"""Remote-access and Wi-Fi operations for the QML interface."""

from __future__ import annotations

from collections.abc import Callable


class RemoteAccessService:
    def __init__(self, publish: Callable[[str, str, str, dict], None]):
        self._publish = publish

    def _send(self, state: str, status: str, url: str = "", **payload) -> None:
        self._publish(state, status, url, payload)

    @staticmethod
    def local_url() -> str:
        try:
            from modules.module_config import load_config
            from modules.module_wifi import WiFiManager

            port = int(load_config().get("ACCESS", {}).get("webui_port", 80))
            host = WiFiManager.HOTSPOT_IP
            return f"http://{host}:{port}" if port != 80 else f"http://{host}"
        except Exception:
            return "http://10.42.0.1"

    def refresh(self) -> None:
        try:
            from modules.module_wifi import _get_manager

            status = _get_manager().get_status()
            mode = str(status.get("mode", "disconnected"))
            if mode == "hotspot":
                self._send("hotspot", "TARS setup hotspot is active", self.local_url())
                return
            if mode == "client":
                try:
                    from modules.module_chatui import _get_tunnel_status

                    tunnel = _get_tunnel_status()
                    if tunnel.get("state") == "active" and tunnel.get("url"):
                        self._send("active", "Remote tunnel is online", str(tunnel["url"]))
                        return
                except Exception:
                    pass
                self._send("ready", f"Connected to {status.get('ssid') or 'Wi-Fi'}")
                return
            self._send("offline", "No Wi-Fi connection")
        except Exception as exc:
            self._send("error", "Unable to read remote-access status", error=str(exc))

    def scan_wifi(self) -> None:
        try:
            from modules.module_wifi import _get_manager

            networks = _get_manager().scan_networks(rescan=True)
            suffix = "s" if len(networks) != 1 else ""
            self._send("networks", f"{len(networks)} network{suffix} found", networks=networks)
        except Exception as exc:
            self._send("error", "Wi-Fi scan failed", error=str(exc))

    def connect_wifi(self, ssid: str, password: str) -> None:
        try:
            from modules.module_wifi import _get_manager

            manager = _get_manager()
            if manager.get_status().get("mode") == "hotspot":
                manager.stop_hotspot()
            if manager.connect(ssid, password):
                self._send("ready", f"Connected to {ssid}")
            else:
                self._send(
                    "error",
                    f"Could not connect to {ssid}",
                    error="Check the password and try again.",
                )
        except Exception as exc:
            self._send("error", f"Could not connect to {ssid}", error=str(exc))

    def start(self) -> None:
        try:
            from modules.module_wifi import _get_manager

            manager = _get_manager()
            if manager.get_status().get("mode") != "client":
                self._send("starting", "Starting TARS setup hotspot")
                if not manager.start_hotspot():
                    raise RuntimeError("NetworkManager could not start the hotspot")
                self._send("hotspot", "TARS setup hotspot is active", self.local_url())
                return

            from modules.module_chatui import (
                _cloudflared_bin,
                _get_tunnel_status,
                _install_cloudflared,
                _start_tunnel,
            )

            tunnel = _get_tunnel_status()
            if tunnel.get("state") == "active" and tunnel.get("url"):
                self._send("active", "Remote tunnel is online", str(tunnel["url"]))
                return
            if not _cloudflared_bin():
                self._send("starting", "Installing remote-access service")
                ok, error = _install_cloudflared()
                if not ok:
                    raise RuntimeError(str(error))
            self._send("starting", "Starting encrypted remote tunnel")
            ok, result = _start_tunnel()
            if not ok:
                raise RuntimeError(str(result))
            self._send("active", "Remote tunnel is online", str(result))
        except Exception as exc:
            self._send("error", "Remote access failed", error=str(exc))

    def stop(self, stop_hotspot: bool) -> None:
        try:
            if stop_hotspot:
                from modules.module_wifi import _get_manager
                _get_manager().stop_hotspot()
            else:
                from modules.module_chatui import _stop_tunnel
                _stop_tunnel()
            self._send("idle", "Remote access stopped")
        except Exception as exc:
            self._send("error", "Unable to stop remote access", error=str(exc))
