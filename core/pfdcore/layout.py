"""Layout/GA drawings beside the Equipment List, linked by tag (app.html after section 10: isLayoutSheet, layoutIndex).

A PDF's sheets are process sheets (PFD, P&ID: they make the Equipment List) or Layout/GA drawings (where the
equipment stands). `split_sheets` sorts them as the app's readPdf does; `layout_index` finds the Equipment
List's tags written on the Layout sheets.
"""
from . import js
from .cost import expand_tags, norm_tag, pad3
from .equipment import EQ_TYPE

LAY_TITLE = r"GENERAL\s+ARRANGEMENT|PLOT\s+PLAN|LAY-?OUT|EQUIPMENT\s+ARRANGEMENT|ARRANGEMENT\s+(?:PLAN|DRAWING)|배치도"
LAY_FILE = r"lay-?out|plot.?plan|general.?arr|(?:^|[^a-z])ga(?:[^a-z]|$)|배치"
LAY_NOT = r"PROCESS\s+FLOW\s+DIAGRAM|PIPING\s+(?:AND|&)\s+INSTRUMENT|\bP\s*&\s*ID\b|MASS\s+BALANCE|STREAM\s+TABLE"
SHORT_TAG = r"(?<![\w-])([A-Z]{2,4})-(\d{2,4})([A-Z]?)(?![\w-])"


def lay_title(items):
    it = next((x for x in items if js.test(LAY_TITLE, x["s"], "i")), None)
    return js.cut(it["s"] if it else "", 40)


def is_layout_sheet(sh, file_name):
    """No drawing number or PFD title, and a title block (or file name) that says Layout / GA / plot plan."""
    if sh.get("dwg") or sh.get("title"):
        return False
    block = " ".join(it["s"] for it in sh["items"] if it["y0"] > 0.7 and it["x0"] > 0.5)
    if js.test(LAY_NOT, block, "i"):
        return False
    return js.test(LAY_TITLE, block, "i") or js.test(LAY_FILE, file_name, "i")


def split_sheets(sheets, roles=None):
    """(process sheets, Layout sheets). roles = {file name: 'layout' | 'pfd'} for files the viewer switched."""
    roles = roles or {}
    proc, lay = [], []
    for sh in sheets:
        sh.setdefault("layTitle", lay_title(sh["items"]))
        role = roles.get(sh["file"])
        (lay if (role == "layout" if role else is_layout_sheet(sh, sh["file"])) else proc).append(sh)
    return proc, lay


def layout_label(sh):
    return f"{sh['file']} {js.jstr(sh['page'])}쪽" + (f" · {sh['layTitle']}" if sh.get("layTitle") else "")


def layout_index(rows, layouts):
    """Per Layout sheet the tags written on it; a tag key → its list rows and the sheets showing it.
    {sheets: [{sh, marks: [{key, rows, how, box}]}], rowsOf: {key: [row index]}, where: {key: [sheet index]}}"""
    rows_of = {}
    for i, r in enumerate(rows):
        if r.get("untagged"):
            continue
        rows_of.setdefault(norm_tag(r["tag"]), []).append(i)
    short = {}   # "PU-001" written without its area → 4300-PU-001 when only one area has that number
    for k in rows_of:
        t = k[5:]
        short[t] = None if t in short else k
    sheets = []
    for sh in layouts:
        marks = []
        for it in sh["items"]:
            if it["y0"] > 0.83 and it["x0"] > 0.6:
                continue   # title block: drawing numbers look like tags
            keys, how = expand_tags(it["s"]), "tag"
            if not keys:
                keys = [k for k in (short.get(f"{m.group(1)}-{pad3(m.group(2))}{m.group(3)}") for m in js.finditer(SHORT_TAG, it["s"].upper())) if k]
                how = "short"
            for k in keys:
                rs = rows_of.get(k) or []
                mc = js.match(r"^\d{4}-([A-Z]+)-", k)
                if not rs and not EQ_TYPE.get(mc.group(1) if mc else None):
                    continue   # neither listed nor an equipment code
                marks.append({"key": k, "rows": rs, "how": how, "box": [it["x0"], it["y0"], it["x1"], it["y1"]]})
        sheets.append({"sh": sh, "marks": marks})
    where = {}
    for j, L in enumerate(sheets):
        for m in L["marks"]:
            w = where.setdefault(m["key"], [])
            if j not in w:
                w.append(j)
    return {"sheets": sheets, "rowsOf": rows_of, "where": where}


def layout_at(index, r):
    """The 'Layout 위치' cell of a row: the Layout sheets its tag is written on."""
    w = None if r.get("untagged") else index["where"].get(norm_tag(r["tag"]))
    return ", ".join(layout_label(index["sheets"][j]["sh"]) for j in w) if w else ""
