"""Прошивка Amlogic через Khadas flash-tool."""

import struct
import subprocess
from pathlib import Path


def image_part_sizes(img: Path) -> list[tuple[str, int]]:
    data = img.read_bytes()[:65536]
    marker = data.find(b"_aml_dtb")
    if marker < 0:
        return []
    rows: list[tuple[str, int]] = []
    for n in range(24):
        name_at = marker + n * 1152
        if name_at + 8 > len(data) or name_at < 264:
            break
        raw = data[name_at : name_at + 32].split(b"\x00", 1)[0]
        if not raw or not raw.replace(b"_", b"").isalnum():
            break
        size = struct.unpack_from("<Q", data, name_at - 264)[0]
        if size > 8 * 1024 * 1024 * 1024:
            break
        rows.append((raw.decode("ascii"), size))
    return rows


def burn_percent(parts: list[tuple[str, int]], name: str, done: bool) -> int | None:
    total = sum(size for _, size in parts)
    if total <= 0:
        return None
    token = name.lower()
    acc = 0
    for part, size in parts:
        if part.lower() == token:
            if done:
                acc += size
            return min(100, int(acc * 100 / total))
        acc += size
    return None


def partition_names(img: Path) -> list[str]:
    blob = img.read_bytes()[:65536]
    text = "".join(chr(b) if 32 <= b < 127 else "\n" for b in blob)
    found = []
    for token in (
        "boot",
        "bootloader",
        "dtbo",
        "logo",
        "odm",
        "product",
        "recovery",
        "system",
        "vbmeta",
        "vendor",
        "_aml_dtb",
    ):
        if token in text and token not in found:
            found.append(token)
    return found


def burn_cmd(
    image: Path,
    erase: bool,
    reset: bool,
    bootloader: bool = False,
    password: str = "",
    parts: str = "all",
) -> list[str]:
    root = Path("/usr/local/bin/aml-burn-tool")
    if root.is_symlink():
        base = root.resolve().parent
    else:
        base = Path.home() / "Downloads/khadas-utils/aml-flash-tool"
    flash = base / "flash-tool"
    if not flash.is_file():
        raise RuntimeError("aml-burn-tool не установлен")
    cmd = [str(flash), f"--img={image}", f"--parts={parts or 'all'}", "--soc=g12a"]
    if erase:
        cmd.append("--wipe")
    if reset:
        cmd.append("--reset=y")
    if password:
        cmd.append(f"--password={password}")
    return cmd


def _port_id(location: int, hub: int) -> str:
    port = (location >> 20) & 0xF
    if port == 0:
        port = 1
    return f"HUB{hub}-{port}"


def usb_devices() -> list[str]:
    proc = subprocess.run(["ioreg", "-p", "IOUSB", "-l", "-w0"], capture_output=True, text=True)
    found = []
    lines = proc.stdout.splitlines()
    hub = 0
    for i, line in enumerate(lines):
        if "USBXHCI@" in line or "USBHostController@" in line:
            hub += 1
        if "IOUSBHostDevice" not in line or "@" not in line:
            continue
        chunk = "\n".join(lines[i : i + 40])
        low = chunk.lower()
        if "amlogic" not in low and "gx-chip" not in low and "worldcup" not in low:
            continue
        try:
            loc_hex = line.split("@", 1)[1].split()[0]
            loc = int(loc_hex, 16)
        except ValueError:
            continue
        dev_id = _port_id(loc, max(hub, 1))
        if dev_id and dev_id not in found:
            found.append(dev_id)
    return found


def usb_connected() -> bool:
    return bool(usb_devices())
