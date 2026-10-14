"""Download every image referenced by the build and write 800w/1600w WebP versions.

Usage: python3 src/fetch_images.py [cache_dir]
Originals are cached outside the repo (default: ~/.cache/leski-originals).
"""
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "assets" / "img"
CACHE = Path(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.cache/leski-originals"))
SIZES = (800, 1600)


def process(item):
    key, url = item
    targets = [OUT / f"{key}-{w}.webp" for w in SIZES]
    if all(t.exists() for t in targets):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    src = CACHE / url.rsplit("/", 1)[-1]
    if not src.exists():
        try:
            urllib.request.urlretrieve(url.replace(" ", "%20"), src)
        except Exception as e:  # keep going; report at the end
            return f"{key}: {e}"
    try:
        im = Image.open(src)
        im = im.convert("RGB")
        for w, t in zip(SIZES, targets):
            copy = im.copy()
            if copy.width > w:
                copy = copy.resize((w, round(copy.height * w / copy.width)), Image.LANCZOS)
            copy.save(t, "WEBP", quality=74 if w == 1600 else 72, method=5)
    except Exception as e:
        return f"{key}: {e}"
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "src" / "data" / "images.json").read_text())
    with ThreadPoolExecutor(8) as ex:
        errors = [e for e in ex.map(process, manifest.items()) if e]
    print(f"{len(manifest)} images, {len(errors)} errors")
    for e in errors:
        print("  ", e)


if __name__ == "__main__":
    main()
