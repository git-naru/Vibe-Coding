"""Drawing numbers, sheet identity and off-page connectors (app.html section 1).

A sheet's text items are dicts {s, x0, y0, x1, y1}: the trimmed text and its box in page fractions
(0..1, origin top left), as `pdf.read_pdf` produces them.
"""
from . import js

DWG_SRC = r"[A-Z0-9][A-Z0-9.]*(?:-[A-Z0-9.&]+)*-(?:PFD|PID|P&ID|PDF)-[A-Z0-9]+"
DWG_1 = "^" + DWG_SRC + "$"
BADGE = r"^\d{2,4}[a-z]?(?:,[a-z])*$"
NOTE_WORDS = ["REFER", "N°", "SEE ", "DOCUMENT", "DETAIL", "LATEST", "REVISION"]
FROM_TO = r"^(FROM|TO)\b"


def norm_dwg(s):
    return js.sub(r"_\d+$", "", js.sub(r"[.,;:)]+$", "", js.trim(s), count=1), count=1)


def canon(d):
    return "-".join(js.num_str(js.number(x)) if js.test(r"^\d+$", x) else x for x in d.split("-"))


def is_badge(s):
    return all(js.test(BADGE, w) for w in js.split(r"\s+", s))


def below(items, i, n):
    a = items[i]
    xs = [b for b in items if b is not a and b["y0"] > a["y0"] + 0.002 and b["y0"] - a["y1"] < 0.025 and abs(b["x0"] - a["x0"]) < 0.02]
    return js.sort(xs, lambda p, q: p["y0"] - q["y0"])[:n]


def above(items, i):
    a = items[i]
    xs = [b for b in items if b is not a and b["y1"] < a["y1"] - 0.002 and a["y0"] - b["y1"] < 0.025 and abs(b["x0"] - a["x0"]) < 0.02]
    xs = js.sort(xs, lambda p, q: q["y1"] - p["y1"])
    return xs[0] if xs else None


def sheet_identity(items):
    """The sheet's own drawing number (title block corner, confirmed by a .dwg path) and its aliases."""
    corner = []
    for i, it in enumerate(items):
        t = norm_dwg(it["s"])
        if it["x0"] > 0.6 and it["y0"] > 0.83 and js.test(DWG_1, t) and not any(js.test(FROM_TO, l["s"]) for l in below(items, i, 2)):
            corner.append(t)
    paths = []
    for it in items:
        if js.test(r"\.dwg", it["s"], "i"):
            paths.extend(norm_dwg(d) for d in js.match_all(DWG_SRC, it["s"]))
    own = next((d for d in corner if d in paths), None) or (corner[0] if corner else None) or (paths[0] if paths else None)
    return {"own": own, "aliases": js.unique(d for d in corner if d != own)}


def connectors_of(items, own, aliases):
    """Drawing numbers cited on the sheet: FROM/TO connectors (with their stream badge) or notes."""
    badges = [it for it in items if is_badge(it["s"])]
    out = []
    for i, it in enumerate(items):
        for d in js.match_all(DWG_SRC, it["s"]):
            d = norm_dwg(d)
            if d == own or d in aliases or js.test(r"\.dwg", it["s"], "i"):
                continue
            nxt = [x["s"] for x in below(items, i, 2)]
            prev_it = above(items, i)
            prev = prev_it["s"] if prev_it else ""
            direction = None
            for s in nxt:
                m = js.match(FROM_TO, js.trim(s))
                if m:
                    direction = m.group(1)
                    break
            note = any(k in it["s"].upper() for k in NOTE_WORDS) or (not direction and it["y0"] > 0.8)
            if note:
                out.append({"kind": "note", "dwg": d})
                continue
            if not direction:
                if it["x1"] < 0.2:
                    direction = "FROM"
                elif it["x0"] > 0.75:
                    direction = "TO"
                else:
                    out.append({"kind": "note", "dwg": d})
                    continue
            cy = (it["y0"] + it["y1"]) / 2
            best = None
            for b in badges:
                dy = abs((b["y0"] + b["y1"]) / 2 - cy)
                dx = b["x0"] - it["x1"] if direction == "FROM" else it["x0"] - b["x1"]
                if dy < 0.012 and dx > -0.02 and dx < 0.25 and (not best or dx < best[0]):
                    best = [dx, b["s"]]
            label = prev if prev and not js.test(DWG_1, norm_dwg(prev)) and not js.test(FROM_TO, prev) and not is_badge(prev) else ""
            detail = next((s for s in nxt if js.test(FROM_TO, js.trim(s))), "")
            out.append({"kind": "flow", "dir": direction, "dwg": d, "stream": best[1] if best else "",
                        "label": js.cut(label, 60), "detail": js.cut(detail, 90)})
    return out


def build_links(sheets):
    """Off-page connections between the sheets read: matched both ways, one-sided, or to drawings not provided."""
    index = {}
    for sh in sheets:
        for d in [sh["dwg"], *sh["aliases"]]:
            if d:
                index.setdefault(d, []).append(sh)
                c = canon(d)
                if c != d:
                    index.setdefault(c, []).append(sh)

    def sheet_of(d):
        xs = index.get(d) or index.get(canon(d)) or []
        return xs[0] if xs else None

    flows, missing = [], {}
    for sh in sheets:
        for c in sh["connectors"]:
            if c["kind"] != "flow":
                continue
            other = sheet_of(c["dwg"])
            check = "?"
            if other:
                want = "TO" if c["dir"] == "FROM" else "FROM"
                mine = {canon(x) for x in [sh["dwg"], *sh["aliases"]] if x}
                ok = any(o["kind"] == "flow" and o["dir"] == want and canon(o["dwg"]) in mine
                         and (not c["stream"] or not o["stream"] or o["stream"] == c["stream"]) for o in other["connectors"])
                check = "matched" if ok else "no return connector"
                if not index.get(c["dwg"]):
                    check += " (dwg no. typo in source)"
            else:
                missing.setdefault(c["dwg"], []).append(sh["key"])
            flows.append({**c, "sheet": sh["dwg"], "sheetKey": sh["key"], "target": other["key"] if other else None, "check": check})
    return {"flows": flows, "missing": missing, "sheetOf": sheet_of,
            "matched": sum(1 for f in flows if f["check"] == "matched"),
            "issues": sum(1 for f in flows if f["target"] and f["check"] != "matched"),
            "missingCount": len(missing)}
