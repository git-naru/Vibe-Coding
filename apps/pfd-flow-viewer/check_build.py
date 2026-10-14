#!/usr/bin/env python3
"""CI check for the single-file app: build it, confirm the demo data was inlined and parses,
and write the page script out so `node --check` can syntax-check it.

    python3 apps/pfd-flow-viewer/check_build.py OUT_DIR
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "dist")
    out.mkdir(parents=True, exist_ok=True)
    page = out / "app.html"
    subprocess.run([sys.executable, str(HERE / "build.py"), str(page)], check=True)
    html = page.read_text(encoding="utf-8")

    assert "__DEMO_DATA__" not in html, "demo data placeholder was not replaced"
    assert "__SAMPLE_DATA__" not in html, "sample data placeholder was not replaced"
    assert '<script id="sample-data" type="application/json">null</script>' in html, "repository build must not carry a real-data sample"
    assert "__CMAP_DATA__" not in html, "CMap placeholder was not replaced"
    cm = re.search(r'<script id="cmap-data" type="application/json">(.*?)</script>', html, re.S)
    assert cm and "Adobe-Korea1-UCS2" in json.loads(cm.group(1)), "Korean CMaps missing from the build"
    demo = re.search(r'<script id="demo-data" type="application/json">(.*?)</script>', html, re.S)
    assert demo, "demo-data script block missing"
    data = json.loads(demo.group(1).replace("<\\/", "</"))
    for key in ("meta", "streams", "nodes", "lines"):
        assert key in data, f"demo data has no '{key}'"

    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 1, f"expected one inline page script, found {len(scripts)}"
    js = out / "app.js"
    js.write_text(scripts[0], encoding="utf-8")
    print(f"ok: {page} ({page.stat().st_size / 1024:.0f} KB), demo streams={len(data['streams'])}, script -> {js}")


if __name__ == "__main__":
    main()
