#!/usr/bin/env python3
"""Build the single-file PFD flow app: inline the synthetic demo flow into app.html.

    python3 apps/pfd-flow-viewer/build.py OUT.html

Publish OUT.html as a claude.ai Artifact with capabilities
{"sample": {"images": true}, "db": {}, "user": {}, "downloads": true}.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent.parent / ".claude/skills/pfd-flow-viewer/examples/demo-steam.json"


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "dist/index.html")
    src = (HERE / "app.html").read_text(encoding="utf-8")
    demo = json.loads(DEMO.read_text(encoding="utf-8"))
    payload = json.dumps(demo, ensure_ascii=False).replace("</", "<\\/")
    assert "__DEMO_DATA__" in src
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src.replace("__DEMO_DATA__", payload, 1), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
