# TARS-AI

<p align="center">
    <a href="https://discord.gg/AmE2Gv9EUt">
      <img alt="Discord Invitation Link" src="https://img.shields.io/discord/1311295890182508605" align="center" />
    </a>
    <a href="https://github.com/TARS-AI-Community/TARS-AI/wiki/Home">
        <img src="https://img.shields.io/badge/Docs-grey?style=flat-square&logo=readthedocs&logoColor=white" alt="Documentation" align="center" />
    </a>
</p>
<p align="center">
  <a href="https://github.com/TARS-AI-Community/TARS-AI">
    <img width=90% alt="" src="https://github.com/TARS-AI-Community/TARS-AI/blob/V2/media/tars-banner.png" />
  </a>
</p>

<p align="center">
  A recreation of the robot TARS from <i>Interstellar</i>, featuring AI capabilities.
</p>

---

## 🚀 Getting Started

- Start with the V2 release documentation:
  [`Documentation/release-documentation-index.txt`](Documentation/release-documentation-index.txt)
- Fresh Raspberry Pi setup:
  [`Documentation/installation-and-first-run.txt`](Documentation/installation-and-first-run.txt)
- Hardware troubleshooting:
  [`Documentation/troubleshooting-flowcharts.txt`](Documentation/troubleshooting-flowcharts.txt)

The `v2.0.0-rc1` release candidate is not certified or tagged until the physical
robot passes [`Documentation/release-checklist-v2.0.0-rc1.txt`](Documentation/release-checklist-v2.0.0-rc1.txt).

### TARS-AI V2 interface

The supported on-device interface is PySide6/QML. From the repository root on
the Raspberry Pi:

```bash
./tars-launcher.sh
```

For a terminal-only diagnostic run:

```bash
./tars-launcher.sh --terminal
```

Run the QML servo calibration tool with:

```bash
source src/.venv/bin/activate
python src/app-servotester-qml.py --fullscreen --hardware
```

Run the automated release suite before applying servo power after an upgrade:

```bash
source src/.venv/bin/activate
python tools/run_release_tests.py --strict
```

Back up `.env`, configuration/calibration, memory, wake templates, and servo state
before updating. The complete procedure is in
[`Documentation/backup-and-restoration.txt`](Documentation/backup-and-restoration.txt).

The retired Pygame interface is preserved under `legacy/pygame/` for source
history only. It is not installed or loaded by TARS-AI V2.

---

## 🤝 Contributing

- Join the community on Discord:
  👉 https://discord.gg/AmE2Gv9EUt

---

## 📜 License

This project is licensed under **Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0)**.

You may:
- Build and modify your own TARS robot
- Share improvements and derivatives
- Use the project for personal, educational, and research purposes

You may **not** use this project for commercial purposes without explicit permission from the authors.
Commercial use includes, but is not limited to:

- Selling 3D printed parts, kits, or complete robots
- Selling or distributing STL / CAD files for money
- Offering paid assembly, customization, or installation services
- Monetized YouTube, Social Media, Patreon, or subscription content that distributes project files or derivatives
- Using this project in paid products, commercial research, or corporate projects
- Integrating this project into commercial software or hardware products
- Selling derivatives or modified versions of the hardware or software

If you are unsure whether your use case is commercial, assume it is and request permission from the authors.

See the [LICENSE](./LICENSE) file for details.

---

## 🧾 Attribution

Please follow the attribution guidelines when sharing or publishing derivative work:

👉 [ATTRIBUTION.md](./ATTRIBUTION.md)

---

