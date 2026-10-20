# USB Burning Tool for macOS

Прошивка Amlogic eMMC через Khadas `aml-flash-tool` (VIM3 / VIM3L, `--soc=g12a`). UI как у Amlogic USB Burning Tool V2.

Распаковка и сборка образов: [multi-image-kitchen-macos](https://github.com/VsevolodVasin/multi-image-kitchen-macos).

## Install

```bash
git clone https://github.com/VsevolodVasin/usb-burning-tool-macos.git
cd usb-burning-tool-macos
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./"Burning Tool.command"
```

Либо: `.venv/bin/python -m burn_tool [/path/to/image.img]`

Нужен [Khadas aml-flash-tool](https://github.com/khadas/utils/tree/master/aml-flash-tool) (`aml-burn-tool` в `/usr/local/bin`).

## DMG

```bash
./scripts/build_dmg.sh
```

Готовые сборки: [Releases](https://github.com/VsevolodVasin/usb-burning-tool-macos/releases).

Если macOS пишет, что приложение повреждено или не может проверить разработчика:

```bash
./scripts/fix-gatekeeper.sh "/Applications/Burning Tool.app"
```

## License

GPL-3.0. Подробности: [THIRD_PARTY.md](THIRD_PARTY.md).
