#!/usr/bin/env python3
"""Build a single-file PFD flow viewer from a data JSON and the viewer template.

Usage:
    python3 build_viewer.py data.json out.html [--template path] [--strict]

What it does:
  1. Validates the data (stream references, node ids, value keys, geometry inside the viewBox).
  2. Recomputes every `checks` entry (mass balance) and prints the result.
  3. Warns about overlapping stream badges / node boxes so the layout can be fixed before publishing.
  4. Injects the JSON into assets/viewer-template.html and writes the page.

Exit code is 1 when there are errors (or warnings with --strict).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "viewer-template.html"

VALUE_KEYS = {
    "dm", "dv", "nm", "nv", "nxm", "nxv", "nnm", "nnv", "dsm", "dsv", "dxm", "dxv", "dnm", "dnv",
    "rho", "T", "P", "sol", "liq", "li", "pH", "DF", "RT",
}


def num(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def badge_box(lab, text):
    w = 20 + len(text) * 8
    return (lab[0] - w / 2, lab[1] - 11, lab[0] + w / 2, lab[1] + 11)


def overlap(a, b, pad=1):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    a = ap.parse_args()

    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    errors, warns = [], []

    meta = data.get("meta", {})
    cats = data.get("categories", {})
    streams = data.get("streams", {})
    nodes = data.get("nodes", [])
    node_info = data.get("nodeInfo", {})
    lines = data.get("lines", [])
    vw, vh = meta.get("viewBox", [1600, 900])

    if not meta.get("docTitle"):
        errors.append("meta.docTitle is required (2-4 word page name)")
    if not cats:
        errors.append("categories is empty")

    # streams
    for sid, s in streams.items():
        if s.get("cat") not in cats:
            errors.append(f"stream {sid}: unknown category {s.get('cat')!r}")
        for k in (s.get("v") or {}):
            if k not in VALUE_KEYS:
                errors.append(f"stream {sid}: unknown value key {k!r} (use extraProps for custom rows)")
        if not s.get("info") and not s.get("v") and not s.get("rows"):
            warns.append(f"stream {sid}: no values (v/rows) — panel will show only route/notes")
        if not s.get("sheet"):
            warns.append(f"stream {sid}: no source sheet")

    # nodes
    ids = [n["id"] for n in nodes]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"duplicate node id {dup}")
    bar_nodes = {b.get("node") for b in data.get("bars", []) if b.get("node")}
    for nid in node_info:
        if nid not in ids and nid not in bar_nodes:
            warns.append(f"nodeInfo {nid}: no node/bar with that id (unreachable)")
    for nid in ids:
        if nid not in node_info:
            warns.append(f"node {nid}: no nodeInfo (box is not clickable)")
    for nid, n in node_info.items():
        for k in (n.get("links") or []) + (n.get("kpiStreams") or []):
            if k not in streams:
                errors.append(f"nodeInfo {nid}: links unknown stream {k}")

    # lines
    drawn = set()
    for i, ln in enumerate(lines):
        sid = ln.get("s")
        if sid is not None and sid not in streams:
            errors.append(f"line #{i}: unknown stream {sid}")
        if sid:
            drawn.add(sid)
        if sid is None and not ln.get("cat"):
            errors.append(f"line #{i}: decorative line needs 'cat'")
        if ln.get("cat") and ln["cat"] not in cats:
            errors.append(f"line #{i}: unknown category {ln['cat']}")
        for x, y in ln["pts"]:
            if not (0 <= x <= vw and 0 <= y <= vh):
                errors.append(f"line #{i} ({sid}): point {x},{y} outside viewBox")
    for sid, s in streams.items():
        if sid not in drawn and not s.get("info") and s.get("drawnAs") not in drawn:
            warns.append(f"stream {sid}: not drawn on the diagram (reachable only from the chip list)")

    # geometry overlaps
    boxes = [(f"node {n['id']}", (n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"])) for n in nodes]
    for n in nodes:
        if n["x"] < 0 or n["y"] < 0 or n["x"] + n["w"] > vw or n["y"] + n["h"] > vh:
            errors.append(f"node {n['id']}: outside viewBox")
    badges = []
    for ln in lines:
        if ln.get("s") and ln.get("lab") and ln["s"] in streams:
            text = streams[ln["s"]].get("label") or ln["s"]
            badges.append((f"badge {text}", badge_box(ln["lab"], text)))
    for i, (na, ba) in enumerate(badges):
        for nb, bb in badges[i + 1:]:
            if overlap(ba, bb):
                warns.append(f"overlap: {na} ↔ {nb}")
        for nn, bn in boxes:
            if overlap(ba, bn, pad=0):
                warns.append(f"overlap: {na} ↔ {nn}")
    for i, (na, ba) in enumerate(boxes):
        for nb, bb in boxes[i + 1:]:
            if overlap(ba, bb, pad=0):
                warns.append(f"overlap: {na} ↔ {nb}")
    # line segments running through a node box (touching its edge is fine)
    for ln in lines:
        pts = ln["pts"]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            seg = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            for nn, (bx0, by0, bx1, by1) in boxes:
                inner = (bx0 + 2, by0 + 2, bx1 - 2, by1 - 2)
                if overlap(seg, inner, pad=0):
                    warns.append(f"line {ln.get('s') or ln.get('cat')} crosses {nn}")

    # balance checks
    report = []
    for c in data.get("checks", []):
        f = c.get("field", "dm")
        tol = c.get("tol", 1)
        lv = [num((streams.get(k, {}).get("v") or {}).get(f)) for k in c["lhs"]]
        rv = [num((streams.get(k, {}).get("v") or {}).get(f)) for k in c["rhs"]]
        for k in c["lhs"] + c["rhs"]:
            if k not in streams:
                errors.append(f"check {c['name']}: unknown stream {k}")
        if None in lv or None in rv:
            warns.append(f"check {c['name']}: missing '{f}' value in some streams")
            continue
        ls, rs = sum(lv), sum(rv)
        ok = abs(ls - rs) <= tol
        report.append(f"  {'OK ' if ok else 'BAD'} {c['name']}: {ls:g} vs {rs:g} {c.get('unit', '')} (diff {abs(ls - rs):g}, tol {tol})")
        if not ok:
            warns.append(f"check {c['name']}: imbalance {abs(ls - rs):g} — keep original values, explain in notes")

    print(f"streams={len(streams)} nodes={len(nodes)} lines={len(lines)} checks={len(data.get('checks', []))}")
    if report:
        print("balance:")
        print("\n".join(report))
    for w in warns:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)

    if errors or (a.strict and warns):
        sys.exit(1)

    tpl = Path(a.template).read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = meta["docTitle"].replace("<", "&lt;")
    page = tpl.replace("__DOC_TITLE__", title, 1).replace("__PFD_DATA__", payload, 1)
    Path(a.out).write_text(page, encoding="utf-8")
    print(f"wrote {a.out} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
