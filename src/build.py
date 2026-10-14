"""Build the Le Ski site into ./site.  Usage: python3 src/build.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import lib  # noqa: E402
from pages_home import build_home  # noqa: E402

BUILDERS = [build_home]

try:
    from pages_chalets import BUILDERS as CHALET_BUILDERS
    BUILDERS += CHALET_BUILDERS
except ImportError:
    pass
try:
    from pages_content import BUILDERS as CONTENT_BUILDERS
    BUILDERS += CONTENT_BUILDERS
except ImportError:
    pass


def main():
    for b in BUILDERS:
        b()
    manifest = lib.DATA / "images.json"
    manifest.write_text(json.dumps(dict(sorted(lib.IMAGE_MANIFEST.items())), indent=1))
    pages = sorted(p.relative_to(lib.SITE) for p in lib.SITE.rglob("index.html"))
    print(f"Built {len(pages)} pages, {len(lib.IMAGE_MANIFEST)} images referenced")


if __name__ == "__main__":
    main()
