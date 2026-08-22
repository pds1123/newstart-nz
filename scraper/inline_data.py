"""Inline the built JSON into the standalone HTML pages.

The frontend has no build step — data lives directly in the file as
`const SUBURB_DATA = [...]` and `const RAW_AREAS = {...}`. This swaps those
assignments for the current contents of data/.

Usage:  python scraper/inline_data.py
"""
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")

TARGETS = {
    "frontend/prototype_v1.html": ["SUBURB_DATA", "RAW_AREAS"],
    "frontend/auckland_map.html": ["SUBURB_DATA"],
}

SOURCES = {
    "SUBURB_DATA": os.path.join(DATA, "suburbs.json"),
    "RAW_AREAS": os.path.join(DATA, "raw_areas.json"),
}

# A JSON array opens with [ and an object with {; match whichever this const holds.
PATTERN = r"const {name} = [\[{{].*?[\]}}];"


def main():
    for rel, consts in TARGETS.items():
        path = os.path.join(REPO, rel)
        html = open(path).read()
        for name in consts:
            payload = open(SOURCES[name]).read().strip()
            pattern = PATTERN.format(name=name)
            if not re.search(pattern, html, flags=re.DOTALL):
                print(f"  ! {rel}: no `const {name}` assignment found, skipped")
                continue
            html = re.sub(pattern, f"const {name} = {payload};", html,
                          count=1, flags=re.DOTALL)
        open(path, "w").write(html)
        sizes = ", ".join(f"{n}={len(json.load(open(SOURCES[n]))):,} entries"
                          if isinstance(json.load(open(SOURCES[n])), list)
                          else f"{n}={len(json.load(open(SOURCES[n])))} keys"
                          for n in consts)
        print(f"  {rel}  ({sizes})")


if __name__ == "__main__":
    main()
