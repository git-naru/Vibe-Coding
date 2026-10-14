#!/usr/bin/env python3
"""Compare pfdcore with the app on your own files (real drawings stay on your machine; nothing is written).

    python core/tests/compare_app.py A.pdf B.pdf ... [--cost EQ-COST.xlsx] [--cmaps] [--show 10]

Runs the app's page script (pdf.js 3.11.174, SheetJS 0.18.5; see parity/harness.cjs) and pfdcore on the same
inputs and reports, per sheet, text items that differ, then the Equipment List, sheet links and (with --cost)
the cost matching. Exit status 1 when anything differs. --cmaps compares the reading the app would do with
pdf.js CMap files (pfdcore cmap_fonts="read").
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from conftest import _clean, diff, run_app  # noqa: E402

from pfdcore import cost, equipment, layout, pdf, sheets, xlsx  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--cost", help="manual equipment list with costs (.xlsx/.csv)")
    ap.add_argument("--cmaps", action="store_true", help="compare with pdf.js given its CMap files")
    ap.add_argument("--show", type=int, default=8, help="differences to print per part")
    a = ap.parse_args()
    files = [str(Path(p).resolve()) for p in a.pdfs]

    t = time.time()
    app = run_app(("withCMaps();" if a.cmaps else "") + f"""
const files = {json.dumps(files)};
for (let i = 0; i < files.length; i++) {{ const e = fileEntry(files[i], i + 1); e.ok = true; S.files.push(e); await readPdf(e); }}
const links = buildLinks(S.sheets); buildEquipment();
const LX = S.layouts.length ? layoutIndex() : null;
const out = {{sheets: [...S.sheets, ...S.layouts].map(s => ({{key: s.key, items: s.items, imgs: s.imgs, dwg: s.dwg, title: s.title}})),
  layouts: S.layouts.map(s => s.key), lay: LX && {{marks: LX.sheets.map(L => L.marks), where: LX.where}},
  links: {{flows: links.flows, missing: links.missing, matched: links.matched, issues: links.issues, missingCount: links.missingCount}},
  eq: {{rows: EQ.rows, refsMissing: EQ.refsMissing, areaNames: EQ.areaNames}}}};
{f"const l = parseCostWorkbook(workbook({json.dumps(str(Path(a.cost).resolve()))})); out.cost = computeCosts({{list: l, unit: l ? l.unit : '', edits: {{}}, pick: {{}}, ai: {{}}}}, EQ.rows);" if a.cost else ""}
return out;""", timeout=3600)
    t_app = time.time() - t

    t = time.time()
    shs = []
    for i, f in enumerate(files):
        shs.extend(pdf.read_pdf(f, file_id=i + 1, cmap_fonts="read" if a.cmaps else "app"))
    shs, lays = layout.split_sheets(shs)
    links = sheets.build_links(shs)
    eq = equipment.build_equipment(shs)
    LX = layout.layout_index(eq["rows"], lays) if lays else None
    lay = LX and {"marks": [L["marks"] for L in LX["sheets"]], "where": LX["where"]}
    t_py = time.time() - t

    bad = 0
    print(f"app {t_app:.1f}s (incl. Node start) · pfdcore {t_py:.1f}s · sheets app {len(app['sheets'])} / pfdcore {len(shs) + len(lays)}")
    print(f"  Layout/GA sheets: app {app['layouts']} / pfdcore {[s['key'] for s in lays]}")
    bad += app["layouts"] != [s["key"] for s in lays]
    for s_app, s_py in zip(app["sheets"], shs + lays):
        d = diff(_clean(s_app["items"]), _clean(s_py["items"]))
        flag = "OK " if not d else "DIFF"
        bad += bool(d)
        print(f"  {flag} {s_py['key']}: items {len(s_app['items'])} / {len(s_py['items'])}, dwg {s_py['dwg']}"
              + (f", warnings {s_py['warnings']}" if s_py["warnings"] else "") + (f", {len(d)} differences" if d else ""))
        for x in d[:a.show]:
            print("       ", x)
    for name, x, y in [("sheet links", app["links"], links), ("Equipment List", app["eq"], eq), ("Layout tags", app["lay"], lay)]:
        d = diff(_clean(x), _clean(y))
        bad += bool(d)
        print(f"  {'OK ' if not d else 'DIFF'} {name}" + (f": {len(d)} differences" if d else f" ({len(eq['rows'])} rows)" if name == "Equipment List" else ""))
        for z in d[:a.show]:
            print("       ", z)
    if a.cost:
        lst = cost.parse_cost_workbook(xlsx.read_workbook(a.cost))
        K = cost.compute_costs({"list": lst, "unit": lst["unit"] if lst else "", "edits": {}, "pick": {}, "ai": {}}, eq["rows"])
        d = diff(_clean(app.get("cost")), _clean(K))
        bad += bool(d)
        print(f"  {'OK ' if not d else 'DIFF'} cost matching" + (f": {len(d)} differences" if d else f" (PFD total {K['pfd']:,.2f})" if K else ""))
        for z in d[:a.show]:
            print("       ", z)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
