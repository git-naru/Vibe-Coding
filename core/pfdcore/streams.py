"""Stream-table rows → viewer fields (app.html section 2): text-layer tables, XLSX tables and the row mapping
shared with image transcription."""
from . import js


def dash(v):
    return v is None or v in ("", "-", "–")


def num_parse(v, decimal_comma):
    """A number written with decimal points (1,562.5) or decimal commas (1,06 / 143,61); NaN when it is not one."""
    if dash(v):
        return js.NaN
    s = js.sub(r"\s", "", js.trim(js.jstr(v)))
    if not js.test(r"^-?[\d.,]+$", s):
        return js.NaN
    s = s.replace(".", "").replace(",", ".", 1) if decimal_comma else s.replace(",", "")
    return js.parse_float(s)


def _at(xs, i):
    return xs[i] if 0 <= i < len(xs) else None


_FLOW_KEYS = {"nom": {"avg": ["nm", "nv"], "max": ["nxm", "nxv"], "min": ["nnm", "nnv"]},
              "des": {"avg": ["dsm", "dsv"], "max": ["dxm", "dxv"], "min": ["dnm", "dnv"]}}


def map_rows(rows, ids, col_values):
    """rows: [{label, unit}], col_values[id] = [value per row] → {id: {v, comp, compSolids, extraProps}}."""
    res = {}
    for i in ids:
        res[i] = {"v": {}, "comp": [], "compSolids": [], "extraProps": []}
    sec, sub = "", "avg"
    for ri, r in enumerate(rows):
        label = r.get("label")
        L = js.trim(js.sub(r"\s+", " ", js.jstr(label if js.truthy(label) else "").lower()))
        unit = r.get("unit")
        U = js.trim(js.jstr(unit if js.truthy(unit) else ""))
        if not L:
            continue
        has_vals = any(not dash(_at(col_values.get(i) or [], ri)) for i in ids)
        if js.test("balance flow", L):
            sec, sub = "bal", "avg"
            if not has_vals:
                continue
        elif js.test("maximum design flow", L):
            sec, sub = "des", "max"
            if not has_vals:
                continue
        elif js.test("nominal flow", L):
            sec, sub = "nom", "avg"
            if not has_vals:
                continue
        elif js.test("design flow", L):
            sec, sub = "des", "avg"
            if not has_vals:
                continue
        elif js.test("other values", L):
            sec = "oth"
            if not has_vals:
                continue
        elif js.test("chemical composition", L):
            sec = "cs" if js.test("solid", L) else "cl"
            if not has_vals:
                continue
        elif js.test("^average value", L):
            sub = "avg"
            if not has_vals:
                continue
        elif js.test("^maximum value", L):
            sub = "max"
            if not has_vals:
                continue
        elif js.test("^minimum value", L):
            sub = "min"
            if not has_vals:
                continue
        key = None
        if sec == "bal":
            key = "dm" if js.test("daily mass flow", L) else "dv" if js.test("daily volumetric flow", L) else None
        elif sec in ("nom", "des"):
            m, v = js.test("^mass flow$", L), js.test("^volumetric flow$", L)
            if m or v:
                key = _FLOW_KEYS[sec][sub][0 if m else 1]
        elif sec == "oth":
            if js.test("^density", L) and not js.test("bulk|solid", L):
                key = "rho"
            elif js.test("^temperature", L):
                key = "T"
            elif js.test("^pressure", L):
                key = "P"
            elif js.test("% ?solids", L):
                key = "sol"
            elif js.test("moisture|% ?liquid", L):
                key = "liq"
            elif js.test(r"^li\b|^li\+|^li⁺", L) and js.test("ppm", U, "i"):
                key = "li"
            elif js.test("^ph$", L):
                key = "pH"
            elif js.test("design factor", L):
                key = "DF"
            elif js.test("run time", L):
                key = "RT"
        for i in ids:
            val = _at(col_values.get(i) or [], ri)
            if dash(val):
                continue
            o = res[i]
            if sec == "cl":
                o["comp"].append([label, js.jstr(val), U or "%"])
            elif sec == "cs":
                o["compSolids"].append([label, js.jstr(val), U or "%"])
            elif key:
                o["v"][key] = js.jstr(val)
            else:
                o["extraProps"].append([label, U, js.jstr(val)])
    return res


def looks_decimal_comma(values):
    dc = th = 0
    for v in values:
        s = js.jstr(v if js.truthy(v) else "")
        if js.test(r"^\d+,\d{1,2}$", s):
            dc += 1
        if js.test(r"^\d{1,3}(,\d{3})+(\.\d+)?$", s):
            th += 1
    return dc > th


def parse_text_table(items):
    """Text-layer stream table: header item "Stream", ids on the same row, row labels down the left."""
    h = next((it for it in items if js.test("^stream$", it["s"], "i")), None)
    if not h:
        return None
    head = js.sort([it for it in items if it is not h and abs(it["y0"] - h["y0"]) < 0.006 and it["x0"] > h["x1"] and js.test(r"^\d{2,4}", it["s"])],
                   lambda a, b: a["x0"] - b["x0"])
    if len(head) < 1:
        return None
    unit_it = next((it for it in items if js.test("^unit$", it["s"], "i") and it["y0"] >= h["y0"] - 0.01 and it["y0"] < h["y0"] + 0.04), None)
    first_x = head[0]["x0"]
    centers = [(it["x0"] + it["x1"]) / 2 for it in head]
    bounds = [[(centers[i - 1] + c) / 2 if i else first_x - 0.01, (c + centers[i + 1]) / 2 if i < len(centers) - 1 else c + 0.05]
              for i, c in enumerate(centers)]
    ids = [js.split(r"\s+", it["s"])[0] for it in head]
    row_items = js.sort([it for it in items if it["y0"] > h["y1"] and it["x1"] < first_x - 0.002 and (not unit_it or it["x0"] < unit_it["x0"] - 0.002)],
                        lambda a, b: a["y0"] - b["y0"])
    rows, col_values = [], {}
    for i in ids:
        col_values[i] = []
    last_y = h["y1"]
    for r in row_items:
        if r["y0"] - last_y > 0.05:
            break
        last_y = r["y1"]
        cy = (r["y0"] + r["y1"]) / 2
        unit = ""
        if unit_it:
            u = next((it for it in items if abs((it["y0"] + it["y1"]) / 2 - cy) < 0.004 and abs(it["x0"] - unit_it["x0"]) < 0.02), None)
            unit = (u or {}).get("s") or ""
        rows.append({"label": r["s"], "unit": unit})
        for k, i in enumerate(ids):
            v = next((it for it in items if abs((it["y0"] + it["y1"]) / 2 - cy) < 0.004
                      and bounds[k][0] <= (it["x0"] + it["x1"]) / 2 < bounds[k][1]), None)
            col_values[i].append(v["s"] if v else "")
    if len(rows) < 4:
        return None
    return {"ids": ids, "rows": rows, "colValues": col_values, "source": "text"}


def parse_xlsx_tables(wb):
    """XLSX: a sheet with a "Stream" cell; ids to its right, labels down its column, units in the "Unit" column."""
    out = []
    for name in wb.sheet_names:
        A = wb.aoa(name, raw=False)
        for r in range(len(A)):
            row_r = A[r] or []
            for c in range(len(row_r)):
                if not js.test("^stream$", js.trim(js.jstr(row_r[c])), "i"):
                    continue
                id_cols = []
                for k in range(c + 1, len(row_r)):
                    v = js.trim(js.jstr(row_r[k]))
                    if js.test(r"^\d{2,4}", v):
                        id_cols.append([js.split(r"\s+", v)[0], k])
                if not id_cols:
                    continue
                uc = -1
                for rr in range(r, min(len(A), r + 4)):
                    k = next((j for j, x in enumerate(A[rr] or []) if js.test("^unit$", js.trim(js.jstr(x)), "i")), -1)
                    if k >= 0:
                        uc = k
                        break
                rows, col_values, desc = [], {}, {}
                for i, _ in id_cols:
                    col_values[i] = []
                for rr in range(r + 1, len(A)):
                    row = A[rr] or []
                    lead = [x for x in row[: uc if uc >= 0 else c + 1] if js.trim(js.jstr(x))]
                    label = js.trim(js.jstr(lead[-1] if lead and js.truthy(lead[-1]) else ""))
                    if not label:
                        if len(rows) > 3 and all(not js.trim(js.jstr(x)) for x in row):
                            break
                        continue
                    if js.test("^unit$", js.jstr(_cell(row, uc) or ""), "i") or (rr == r + 1 and not rows and uc >= 0 and not js.trim(js.jstr(_cell(row, uc)))):
                        for i, k in id_cols:
                            if js.trim(js.jstr(_cell(row, k))):
                                desc[i] = js.trim(js.jstr(_cell(row, k)))
                        if not js.test("flow|value", label, "i"):
                            continue
                    rows.append({"label": label, "unit": js.trim(js.jstr(_cell(row, uc) or "")) if uc >= 0 else ""})
                    for i, k in id_cols:
                        v = _cell(row, k)
                        col_values[i].append(js.trim(js.jstr("" if v is None else v)))
                if len(rows) >= 4:
                    out.append({"sheet": name, "ids": [x[0] for x in id_cols], "rows": rows, "colValues": col_values, "desc": desc, "source": "xlsx"})
    return out


def _cell(row, k):
    """row[k] as JavaScript reads it: undefined (None) past the end or at a negative index."""
    return row[k] if 0 <= k < len(row) else None
