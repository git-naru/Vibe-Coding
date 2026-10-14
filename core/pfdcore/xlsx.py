"""Workbooks read the way the app reads them with SheetJS 0.18.5: `XLSX.read` + `sheet_to_json(ws, {header: 1, defval: ''})`.

What matters for the same answers:
- a sheet's rows run over its used range (the `<dimension>` the file declares, else the cells present), so
  row 0 / column 0 are the range's first row and column, not A1, and blank rows inside it are kept;
- `raw=True` gives numbers as stored (dates stay serial numbers), strings, booleans; error cells are '';
- `raw=False` gives the cell text SheetJS formats (`ssf.cell_text`).

.xlsx is read directly from its XML parts; .csv follows SheetJS's guesses for numbers and booleans.
"""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from . import js, ssf

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
_M = "{%s}" % NS["m"]


def _unescape(s):
    """SheetJS unescapexml: the _xHHHH_ escapes Excel writes for control characters."""
    return re.sub(r"_x([0-9a-fA-F]{4})_", lambda m: chr(int(m.group(1), 16)), s)


def _text(el):
    """Plain text of a shared/inline string: its <t>, or the <t> of each rich-text run (phonetic runs skipped)."""
    t = el.find(_M + "t")
    if t is not None and not list(el.findall(_M + "r")):
        return _unescape(t.text or "")
    return _unescape("".join((r.findtext(_M + "t") or "") for r in el.findall(_M + "r")))


def _col(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _addr(a):
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", a.upper())
    return int(m.group(2)) - 1, _col(m.group(1))


def _range(ref):
    a, _, b = ref.partition(":")
    r0, c0 = _addr(a)
    r1, c1 = _addr(b) if b else (r0, c0)
    return min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1)


class Sheet:
    def __init__(self, cells, ref):
        self.cells = cells          # {(r, c): (value, format code)}
        self.ref = ref              # (r0, c0, r1, c1) or None


class Workbook:
    """sheet_names in workbook order; aoa(name, raw) = sheet_to_json(ws, {header: 1, raw, defval: ''})."""

    def __init__(self, sheets, names):
        self.sheets = sheets
        self.sheet_names = names

    def aoa(self, name, raw=True):
        sh = self.sheets[name]
        if sh.ref is None:
            return []
        r0, c0, r1, c1 = sh.ref
        out = []
        for r in range(r0, r1 + 1):
            row = []
            for c in range(c0, c1 + 1):
                cell = sh.cells.get((r, c))
                if cell is None:
                    row.append("")
                    continue
                v, fmt = cell
                if v is None:
                    row.append("")
                elif raw:
                    row.append(v)
                else:
                    row.append(ssf.cell_text(v, fmt))
            out.append(row)
        return out


def _rels(z, path):
    d = Path(path).parent.as_posix()
    rp = f"{d}/_rels/{Path(path).name}.rels"
    if rp not in z.namelist():
        return {}
    out = {}
    for rel in ET.fromstring(z.read(rp)).findall("pr:Relationship", NS):
        t = rel.get("Target")
        out[rel.get("Id")] = t.lstrip("/") if t.startswith("/") else f"{d}/{t}" if d else t
    return out


def read_xlsx(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    wb_path = "xl/workbook.xml"
    root = ET.fromstring(z.read(wb_path))
    rels = _rels(z, wb_path)
    pr = root.find(_M + "workbookPr")
    date1904 = pr is not None and pr.get("date1904") in ("1", "true")
    sst = []
    sst_path = next((p for p in rels.values() if p.endswith("sharedStrings.xml")), "xl/sharedStrings.xml")
    if sst_path in names:
        sst = [_text(si) for si in ET.fromstring(z.read(sst_path)).findall(_M + "si")]
    custom, xf_fmt = {}, []
    st_path = next((p for p in rels.values() if p.endswith("styles.xml")), "xl/styles.xml")
    if st_path in names:
        st = ET.fromstring(z.read(st_path))
        for nf in st.iter(_M + "numFmt"):
            custom[int(nf.get("numFmtId"))] = nf.get("formatCode")
        xfs = st.find(_M + "cellXfs")
        if xfs is not None:
            xf_fmt = [int(x.get("numFmtId") or 0) for x in xfs.findall(_M + "xf")]
    sheets, order = {}, []
    for s in root.find(_M + "sheets").findall(_M + "sheet"):
        name = s.get("name")
        order.append(name)
        path = rels.get(s.get("{%s}id" % NS["r"]))
        if not path or path not in names:
            sheets[name] = Sheet({}, None)
            continue
        ws = ET.fromstring(z.read(path))
        cells, seen = {}, []
        for c in ws.iter(_M + "c"):
            ref = c.get("r")
            t = c.get("t") or "n"
            s_idx = int(c.get("s") or 0)
            fmt = ssf.format_code(xf_fmt[s_idx] if s_idx < len(xf_fmt) else 0, custom)
            v_el = c.find(_M + "v")
            vt = (v_el.text or "") if v_el is not None else None
            if c.get("t") is None and vt is None and c.find(_M + "f") is not None:
                t, vt = "n", "0"   # a formula never calculated: SheetJS reads 0
            if t == "s":
                v = sst[int(vt)] if vt is not None else None
            elif t == "inlineStr":
                is_el = c.find(_M + "is")
                v = _text(is_el) if is_el is not None else ""
            elif t == "str":
                v = _unescape(vt or "")
            elif t == "b":
                v = None if vt is None else vt in ("1", "true", "TRUE")
            elif t in ("e", "d"):
                v = None   # errors read as '' (defval); ISO date cells (t="d") are not written by Excel
            else:
                v = None if vt is None or vt == "" else js.parse_float(vt)
                if js.is_num(v) and float(v).is_integer() and abs(v) < 2**53:
                    v = int(v)
            if ref is None:
                continue
            rc = _addr(ref)
            seen.append(rc)
            if v is not None:
                cells[rc] = (v, fmt)
        dim = ws.find(_M + "dimension")
        if dim is not None and dim.get("ref"):
            rng = _range(dim.get("ref"))
        elif seen:
            rng = (min(r for r, _ in seen), min(c for _, c in seen), max(r for r, _ in seen), max(c for _, c in seen))
        else:
            rng = None
        sheets[name] = Sheet(cells, rng)
    wb = Workbook(sheets, order)
    wb.date1904 = date1904
    return wb


# ---- CSV ---------------------------------------------------------------------------------------
def _csv_value(s):
    """SheetJS's guess for one CSV field: TRUE/FALSE, numbers (thousands commas and % allowed), else text."""
    if s == "":
        return None
    u = s.upper()
    if u == "TRUE":
        return True
    if u == "FALSE":
        return False
    t = s.strip()
    m = re.fullmatch(r"([+-]?)\(?([0-9][0-9,]*(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\)?(%?)", t)
    if m and t:
        x = js.number(t.replace(",", "").replace("%", "").replace("(", "-").replace(")", ""))
        if js.finite(x):
            if m.group(3):
                x /= 100
            return int(x) if float(x).is_integer() and abs(x) < 2**53 else x
    return s


def read_csv(data):
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    cells = {}
    for r, row in enumerate(rows):
        for c, s in enumerate(row):
            v = _csv_value(s)
            if v is not None:
                cells[(r, c)] = (v, "General")
    width = max((len(r) for r in rows), default=0)
    ref = (0, 0, len(rows) - 1, width - 1) if rows and width else None
    return Workbook({"Sheet1": Sheet(cells, ref)}, ["Sheet1"])


def read_workbook(path_or_bytes, name=None):
    """Open .xlsx or .csv (path, or bytes with a file name). .xls (BIFF) is not read."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data, name = bytes(path_or_bytes), name or ""
    else:
        p = Path(path_or_bytes)
        data, name = p.read_bytes(), name or p.name
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if data[:4] == b"PK\x03\x04":
        return read_xlsx(data)
    if ext == "csv" or ext == "txt":
        return read_csv(data)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise ValueError(f"{name}: .xls(구 Excel 형식)는 아직 읽지 못합니다. .xlsx로 저장해 올리세요.")
    raise ValueError(f"{name}: 읽을 수 없는 형식입니다 (.xlsx, .csv).")
