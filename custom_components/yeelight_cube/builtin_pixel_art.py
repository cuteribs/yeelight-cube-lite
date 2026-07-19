"""Built-in Cube Lite pixel art extracted from the official Yeelight app."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path


_PRESET_DIR = Path(__file__).parent / "presets"


def _argb_to_rgb(value: int) -> list[int]:
    """Convert the app's unsigned ARGB integer to an RGB triplet."""
    return [(value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF]


@lru_cache(maxsize=1)
def get_builtin_pixel_arts() -> tuple[dict, ...]:
    """Load the official horizontal and vertical recommendation galleries."""
    result = []
    for orientation, filename in (
        ("Horizontal", "horizontal.json"),
        ("Vertical", "vertical.json"),
    ):
        with (_PRESET_DIR / filename).open(encoding="utf-8") as preset_file:
            groups = json.load(preset_file)

        index = 1
        for group_key in sorted(groups, key=int):
            for item_key in sorted(groups[group_key], key=int):
                argb_pixels = json.loads(groups[group_key][item_key])
                pixels = [
                    {"position": position, "color": _argb_to_rgb(argb)}
                    for position, argb in enumerate(argb_pixels)
                    if argb
                ]
                result.append(
                    {
                        "name": f"Built-in: {orientation} {index:02d}",
                        "pixels": pixels,
                    }
                )
                index += 1
    return tuple(result)


@lru_cache(maxsize=1)
def get_builtin_pixel_art_map() -> dict[str, dict]:
    """Return built-in drawings keyed by their read-only display name."""
    return {art["name"]: art for art in get_builtin_pixel_arts()}
