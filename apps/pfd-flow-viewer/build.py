#!/usr/bin/env python3
"""Build the single-file PFD flow app: inline the synthetic demo flow into app.html.

    python3 apps/pfd-flow-viewer/build.py OUT.html [--sample SAMPLE.json]

--sample inlines a real-data sample ({label, note, flow, equipment}) behind the "실적 샘플 보기" button.
Real project data stays out of this repository: keep the sample file elsewhere and use it only for
the private published build.

Publish OUT.html as a claude.ai Artifact with capabilities
{"sample": {"images": true}, "db": {}, "user": {}, "downloads": true}.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent.parent / ".claude/skills/pfd-flow-viewer/examples/demo-steam.json"


def inline(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=str(HERE / "dist/index.html"))
    ap.add_argument("--sample", help="real-data sample JSON for the private build")
    a = ap.parse_args()
    out = Path(a.out)
    src = (HERE / "app.html").read_text(encoding="utf-8")
    assert "__DEMO_DATA__" in src and "__SAMPLE_DATA__" in src
    demo = json.loads(DEMO.read_text(encoding="utf-8"))
    sample = json.loads(Path(a.sample).read_text(encoding="utf-8")) if a.sample else None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(src.replace("__DEMO_DATA__", inline(demo), 1).replace("__SAMPLE_DATA__", inline(sample), 1), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
