"""Headless dashboard data service for the PySide6/QML interface.

This preserves the original dashboard's Open-Meteo, RSS, ICS, and configured
quote behavior without importing its Pygame/OpenGL presentation layer.
"""

from __future__ import annotations

import configparser
import json
import random
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Callable, Optional


DEFAULT_QUOTES = [
    ("Love is the one thing we're capable of perceiving that transcends dimensions of time and space.", "Interstellar"),
    ("Mankind was born on Earth. It was never meant to die here.", "Interstellar"),
    ("Do not go gentle into that good night. Rage, rage against the dying of the light.", "Interstellar"),
    ("We're explorers, not caretakers.", "Interstellar"),
    ("Somewhere, something incredible is waiting to be known.", "Carl Sagan"),
]

WEATHER_DESCRIPTIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain",
    67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm", 99: "Severe storm",
}


@dataclass(frozen=True)
class DashboardConfig:
    latitude: float = 45.5017
    longitude: float = -73.5673
    timezone: str = "America/Montreal"
    location_name: str = "Montreal"
    language: str = "en"
    country: str = "CA"
    temp_unit: str = "celsius"
    weather_update_interval: int = 600
    news_update_interval: int = 300
    max_news_items: int = 30
    calendar_urls: tuple[str, ...] = ()
    calendar_days_ahead: int = 7
    calendar_max_events: int = 10
    calendar_update_interval: int = 300
    feed_mode: str = "alternate"
    show_weather: bool = True
    show_news: bool = True
    show_quotes: bool = True


def _configuration_path(base_dir: Path) -> Path:
    configured = base_dir / "dashboard.ini"
    return configured if configured.is_file() else base_dir / "dashboard.template.ini"


def _load_configuration(base_dir: Path) -> tuple[DashboardConfig, list[tuple[str, str]], Path]:
    path = _configuration_path(base_dir)
    parser = configparser.ConfigParser(interpolation=None)
    if path.is_file():
        parser.read(path, encoding="utf-8")

    urls = parser.get("Calendar", "ics_urls", fallback="").strip()
    if not urls:
        urls = parser.get("Calendar", "ics_url", fallback="").strip()
    calendar_urls = tuple(url.strip() for url in urls.split(",") if url.strip())

    config = DashboardConfig(
        latitude=parser.getfloat("Location", "latitude", fallback=45.5017),
        longitude=parser.getfloat("Location", "longitude", fallback=-73.5673),
        timezone=parser.get("Location", "timezone", fallback="America/Montreal"),
        location_name=parser.get("Location", "location_name", fallback="Montreal"),
        language=parser.get("Language", "language", fallback="en"),
        country=parser.get("Language", "country", fallback="CA"),
        temp_unit=parser.get("Weather", "temp_unit", fallback="celsius").lower(),
        weather_update_interval=max(60, parser.getint("Weather", "update_interval", fallback=600)),
        news_update_interval=max(60, parser.getint("News", "update_interval", fallback=300)),
        max_news_items=max(1, parser.getint("News", "max_items", fallback=30)),
        calendar_urls=calendar_urls,
        calendar_days_ahead=max(1, parser.getint("Calendar", "days_ahead", fallback=7)),
        calendar_max_events=max(1, parser.getint("Calendar", "max_events", fallback=10)),
        calendar_update_interval=max(60, parser.getint("Calendar", "update_interval", fallback=300)),
        feed_mode=parser.get("Feed", "mode", fallback="alternate").lower(),
        show_weather=parser.getboolean("Display", "show_weather", fallback=True),
        show_news=parser.getboolean("Display", "show_news", fallback=True),
        show_quotes=parser.getboolean("Display", "show_quotes", fallback=True),
    )

    section = f"Quotes_{config.language}"
    if not parser.has_section(section):
        section = "Quotes_en"
    numbered_quotes: list[tuple[int, str, str]] = []
    if parser.has_section(section):
        for key, value in parser.items(section):
            if not key.startswith("quote_") or "|" not in value:
                continue
            try:
                index = int(key.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            text, author = value.rsplit("|", 1)
            numbered_quotes.append((index, text.strip(), author.strip()))
    numbered_quotes.sort(key=lambda item: item[0])
    quotes = [(text, author) for _, text, author in numbered_quotes] or list(DEFAULT_QUOTES)
    return config, quotes, path


class DashboardDataService:
    """Fetch and cache dashboard data on worker threads."""

    def __init__(self, base_dir: Path, on_update: Callable[[dict], None]):
        self.config, self.quotes, self.config_path = _load_configuration(Path(base_dir))
        self._on_update = on_update
        self._lock = threading.Lock()
        self._refreshing = False
        self._stopped = False
        self._last_refresh = 0.0
        self._quote_index = random.randrange(len(self.quotes)) if self.quotes else 0
        self._weather: dict = {}
        self._forecast: list[dict] = []
        self._news: list[dict] = []
        self._calendar: list[dict] = []
        self._errors: list[str] = []

    def _minimum_interval(self) -> int:
        intervals = [self.config.weather_update_interval]
        if self.config.show_news:
            intervals.append(self.config.news_update_interval)
        if self.config.calendar_urls:
            intervals.append(self.config.calendar_update_interval)
        return min(intervals)

    def request_refresh(self, force: bool = False) -> bool:
        with self._lock:
            if self._stopped or self._refreshing:
                return False
            if not force and self._last_refresh and time.time() - self._last_refresh < self._minimum_interval():
                return False
            self._refreshing = True
        self._publish()
        threading.Thread(target=self._refresh_worker, name="QMLDashboardData", daemon=True).start()
        return True

    def rotate_quote(self) -> None:
        with self._lock:
            if self.quotes:
                self._quote_index = (self._quote_index + 1) % len(self.quotes)
        self._publish()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True

    def snapshot(self) -> dict:
        with self._lock:
            quote = self.quotes[self._quote_index] if self.quotes else ("", "")
            return {
                "loading": self._refreshing,
                "error": " · ".join(self._errors),
                "weather": dict(self._weather),
                "forecast": list(self._forecast),
                "news": list(self._news),
                "calendar": list(self._calendar),
                "feed": self._build_feed_locked(),
                "quote": {"text": quote[0], "author": quote[1]},
                "location": self.config.location_name,
                "calendarConfigured": bool(self.config.calendar_urls),
                "lastUpdated": datetime.fromtimestamp(self._last_refresh).strftime("%I:%M %p").lstrip("0") if self._last_refresh else "",
                "configFile": self.config_path.name,
            }

    def _publish(self) -> None:
        if not self._stopped:
            self._on_update(self.snapshot())

    def _refresh_worker(self) -> None:
        jobs = {}
        errors: list[str] = []
        try:
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="DashboardFetch") as executor:
                if self.config.show_weather:
                    jobs[executor.submit(self._fetch_weather)] = "Weather"
                if self.config.show_news:
                    jobs[executor.submit(self._fetch_news)] = "News"
                if self.config.calendar_urls:
                    jobs[executor.submit(self._fetch_calendar)] = "Calendar"

                for future in as_completed(jobs):
                    name = jobs[future]
                    try:
                        result = future.result()
                        with self._lock:
                            if name == "Weather":
                                self._weather, self._forecast = result
                            elif name == "News":
                                self._news = result
                            elif name == "Calendar":
                                self._calendar = result
                    except Exception as exc:
                        errors.append(f"{name}: {exc}")
        finally:
            with self._lock:
                self._errors = errors
                self._last_refresh = time.time()
                self._refreshing = False
            self._publish()

    def _fetch_weather(self) -> tuple[dict, list[dict]]:
        params = {
            "latitude": self.config.latitude,
            "longitude": self.config.longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
            "timezone": self.config.timezone,
            "forecast_days": 5,
        }
        if self.config.temp_unit == "fahrenheit":
            params["temperature_unit"] = "fahrenheit"
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "TARS-AI-Dashboard/2.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        current = payload.get("current", {})
        code = int(current.get("weather_code", -1))
        unit = "°F" if self.config.temp_unit == "fahrenheit" else "°C"
        weather = {
            "temperature": round(float(current.get("temperature_2m", 0))),
            "feelsLike": round(float(current.get("apparent_temperature", 0))),
            "humidity": int(current.get("relative_humidity_2m", 0)),
            "wind": round(float(current.get("wind_speed_10m", 0))),
            "condition": WEATHER_DESCRIPTIONS.get(code, "Unknown"),
            "code": code,
            "unit": unit,
            "location": self.config.location_name,
        }

        daily = payload.get("daily", {})
        dates = daily.get("time", [])
        forecast = []
        for index, date_value in enumerate(dates[:5]):
            try:
                day = datetime.fromisoformat(date_value).strftime("%a").upper()
                day_code = int(daily.get("weather_code", [])[index])
                forecast.append({
                    "day": day,
                    "high": round(float(daily.get("temperature_2m_max", [])[index])),
                    "low": round(float(daily.get("temperature_2m_min", [])[index])),
                    "rain": int(daily.get("precipitation_probability_max", [])[index] or 0),
                    "condition": WEATHER_DESCRIPTIONS.get(day_code, "Unknown"),
                })
            except (IndexError, TypeError, ValueError):
                continue
        return weather, forecast

    def _news_feeds(self) -> list[tuple[str, str]]:
        language = self.config.language
        country = self.config.country
        location = urllib.parse.quote(self.config.location_name)
        suffix = f"hl={language}-{country}&gl={country}&ceid={country}:{language}"
        return [
            ("LOCAL", f"https://news.google.com/rss/headlines/section/geo/{location}?{suffix}"),
            ("TOP", f"https://news.google.com/rss?{suffix}"),
            ("TECH", f"https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?{suffix}"),
            ("SCIENCE", f"https://news.google.com/rss/headlines/section/topic/SCIENCE?{suffix}"),
            ("WORLD", f"https://news.google.com/rss/headlines/section/topic/WORLD?{suffix}"),
        ]

    @staticmethod
    def _element_text(item, names: tuple[str, ...]) -> str:
        for name in names:
            element = item.find(name)
            if element is not None and element.text:
                return element.text.strip()
        return ""

    def _fetch_news_feed(self, source: str, url: str) -> list[dict]:
        request = urllib.request.Request(url, headers={"User-Agent": "TARS-AI-Dashboard/2.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            xml_data = response.read().decode("utf-8", errors="ignore")
        root = ET.fromstring(xml_data)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        stories = []
        for item in items[:10]:
            title = self._element_text(item, ("title", "{http://www.w3.org/2005/Atom}title"))
            if not title:
                continue
            description = self._element_text(
                item,
                (
                    "description",
                    "{http://www.w3.org/2005/Atom}summary",
                    "{http://www.w3.org/2005/Atom}content",
                    "{http://purl.org/rss/1.0/modules/content/}encoded",
                ),
            )
            title = re.sub(r"<[^>]+>", "", unescape(title))
            description = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(description)))[:320]
            date_text = self._element_text(
                item, ("pubDate", "{http://www.w3.org/2005/Atom}published")
            )
            stories.append({
                "kind": "NEWS",
                "title": title,
                "detail": description,
                "meta": source,
                "date": date_text,
            })
        return stories

    def _fetch_news(self) -> list[dict]:
        stories: list[dict] = []
        failures = 0
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="RSSFetch") as executor:
            futures = {
                executor.submit(self._fetch_news_feed, source, url): source
                for source, url in self._news_feeds()
            }
            for future in as_completed(futures):
                try:
                    stories.extend(future.result())
                except Exception:
                    failures += 1
        if not stories and failures:
            raise RuntimeError("news feeds unavailable")
        random.shuffle(stories)
        return stories[: self.config.max_news_items]

    def _fetch_calendar(self) -> list[dict]:
        events = []
        failures = 0
        for url in self.config.calendar_urls:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "TARS-AI-Dashboard/2.0"})
                with urllib.request.urlopen(request, timeout=15) as response:
                    events.extend(self._parse_ics(response.read().decode("utf-8", errors="ignore")))
            except Exception:
                failures += 1
        if not events and failures:
            raise RuntimeError("configured calendar unavailable")

        now = datetime.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        future_limit = now + timedelta(days=self.config.calendar_days_ahead)
        upcoming = [
            event for event in events
            if (
                start_of_today <= event["start"] <= future_limit
                or (
                    event.get("end") is not None
                    and event["start"] < now
                    and event["end"] >= now
                )
            )
        ]
        upcoming.sort(key=lambda event: event["start"])
        return [self._calendar_view(event, now) for event in upcoming[: self.config.calendar_max_events]]

    @staticmethod
    def _parse_ics_datetime(value: str) -> Optional[datetime]:
        value = value.strip().replace("Z", "")
        try:
            if len(value) == 8:
                return datetime.strptime(value, "%Y%m%d")
            if len(value) >= 15:
                return datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        except ValueError:
            pass
        return None

    def _parse_ics(self, data: str) -> list[dict]:
        lines = data.replace("\r\n ", "").replace("\r\n\t", "").splitlines()
        events: list[dict] = []
        current: Optional[dict] = None
        for raw_line in lines:
            line = raw_line.strip()
            if line == "BEGIN:VEVENT":
                current = {}
                continue
            if line == "END:VEVENT":
                if current and current.get("start") and current.get("summary"):
                    events.append(current)
                current = None
                continue
            if current is None or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key_name = key.split(";", 1)[0]
            clean = value.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")
            if key_name == "SUMMARY":
                current["summary"] = clean
            elif key_name == "LOCATION":
                current["location"] = clean
            elif key_name in ("DTSTART", "DTEND"):
                parsed = self._parse_ics_datetime(value)
                if parsed:
                    current["start" if key_name == "DTSTART" else "end"] = parsed
                    if key_name == "DTSTART":
                        current["all_day"] = len(value.strip()) == 8
        return events

    @staticmethod
    def _calendar_view(event: dict, now: datetime) -> dict:
        start = event["start"]
        if start.date() == now.date():
            day = "TODAY"
        elif start.date() == (now + timedelta(days=1)).date():
            day = "TOMORROW"
        else:
            day = start.strftime("%a %b %d").upper()
        when = day if event.get("all_day") else f"{day} · {start.strftime('%I:%M %p').lstrip('0')}"
        return {
            "kind": "CALENDAR",
            "title": event.get("summary", "Untitled event"),
            "detail": event.get("location", ""),
            "meta": when,
            "date": start.isoformat(),
        }

    def _build_feed_locked(self) -> list[dict]:
        if self.config.feed_mode == "news":
            return list(self._news)
        if self.config.feed_mode == "calendar":
            return list(self._calendar)
        combined: list[dict] = []
        length = max(len(self._news), len(self._calendar))
        for index in range(length):
            if index < len(self._calendar):
                combined.append(self._calendar[index])
            if index < len(self._news):
                combined.append(self._news[index])
        return combined

