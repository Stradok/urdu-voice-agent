import re
import subprocess

_DEVICE_LINE = re.compile(r"^card (\d+): (\S+) \[([^\]]+)\], device (\d+): ([^\[]+)\[([^\]]+)\]")


def _list_devices(command: str) -> list[dict]:
    try:
        listing = subprocess.run([command, "-l"], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    devices = []
    for line in listing.splitlines():
        match = _DEVICE_LINE.match(line)
        if not match:
            continue
        card_idx, _card_id, card_name, device_idx, _dev_name, dev_desc = match.groups()
        devices.append({
            "id": f"plughw:{card_idx},{device_idx}",
            "label": f"{card_name.strip()} - {dev_desc.strip()}",
        })
    return devices


def list_capture_devices() -> list[dict]:
    return _list_devices("arecord")


def list_playback_devices() -> list[dict]:
    return _list_devices("aplay")


def resolve_capture_device(configured: str) -> str:
    """"auto" prefers a USB capture device (e.g. a webcam mic) over the motherboard's
    analog input, which on a desktop is frequently left with nothing plugged into it."""
    if configured and configured != "auto":
        return configured

    try:
        listing = subprocess.run(["arecord", "-l"], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "default"

    usb_match = re.search(r"card (\d+):.*USB", listing)
    if usb_match:
        return f"plughw:{usb_match.group(1)},0"
    return "default"


def resolve_playback_device(configured: str) -> str:
    if configured and configured != "auto":
        return configured
    return "default"
