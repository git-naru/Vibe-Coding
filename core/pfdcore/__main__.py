"""Command line: the app's Equipment List and investment estimate without a browser.

    python -m pfdcore equipment A.pdf B.pdf [--cost EQ-COST.xlsx] [--bundle FLOW.json] [--xlsx OUT.xlsx] [--json OUT.json]
    python -m pfdcore estimate --rows EST.json --record A.json --record B.json [--rates RATES.xlsx] [--xlsx OUT.xlsx] [--json OUT.json]

`equipment` reads PFD PDFs (and a manual equipment list with costs) into the Equipment List, as the app does.
`estimate` takes record JSON files in the app's record shape ({bundle, equipment: {rows, cost}, qty, est}; see
data-schema.md): --rows is the estimate project's record, each --record a recorded project's latest record.
"""
import argparse
import json
import sys
from pathlib import Path

from . import cost, equipment, estimate, export, js, pdf, sheets, xlsx


def _json(path, value):
    Path(path).write_text(json.dumps(js.plain(value), ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_equipment(a):
    shs = []
    for i, f in enumerate(a.pdfs):
        shs.extend(pdf.read_pdf(f, file_id=i + 1, cmap_fonts="read" if a.cmaps else "app"))
    eq = equipment.build_equipment(shs)
    title = ""
    if a.bundle:
        b = json.loads(Path(a.bundle).read_text(encoding="utf-8"))
        title = equipment.link_equipment_to_flow(eq["rows"], equipment.flow_tabs(b if b.get("tabs") else None, None if b.get("tabs") else b))
    C = K = None
    if a.cost:
        lst = cost.parse_cost_workbook(xlsx.read_workbook(a.cost))
        if not lst:
            print(f"{a.cost}: Tag(또는 설비명)과 금액(또는 단가) 머리글이 있는 표를 찾지 못했습니다.", file=sys.stderr)
        else:
            C = cost.load_cost_list(None, lst, Path(a.cost).name)
            K = cost.compute_costs(C, eq["rows"])
    rows = eq["rows"]
    u = sum(1 for r in rows if r.get("untagged"))
    print(f"설비 {len(rows)}건 (Tag 있음 {len(rows) - u}, 미확인 {u}) · PFD {len(shs)}장 · 도면 미포함 참조 {len(eq['refsMissing'])}건")
    for w in sorted({w for s in shs for w in s["warnings"]}):
        print("주의:", {"cmap-font": "CMap 파일이 필요한 글꼴의 글자는 앱처럼 읽지 않았습니다 (--cmaps로 읽기)", "vertical": "세로쓰기 글자", "rtl": "오른쪽에서 왼쪽 글자"}.get(w, w))
    if K:
        print(f"설비비: PFD 설비 합계 {js.fmt_cost(K['pfd'])} {C['unit']} · 수동 목록 {len(C['list']['items'])}행 {js.fmt_cost(K['total'])} · PFD에 없음 {len(K['unmatched'])}행")
    if a.json:
        _json(a.json, {"rows": rows, "refsMissing": eq["refsMissing"], "areaNames": eq["areaNames"], "file": ", ".join(Path(f).name for f in a.pdfs),
                       "sheets": len(shs), "cost": C})
    if a.xlsx:
        files = {}
        for s in shs:
            files[s["file"]] = files.get(s["file"], 0) + 1
        export.equipment_workbook(rows, eq["refsMissing"], eq["areaNames"], cost=C, costs=K, mb_title=title,
                                  inputs=", ".join(f"{n} ({k}장)" for n, k in files.items()), vision=f"0/{len(shs)}장 실행").save(a.xlsx)
        print("Excel:", a.xlsx)
    return 0


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_estimate(a):
    X = _load(a.rows)
    rows = (X.get("equipment") or {}).get("rows") or []
    projects, refs = [], {}
    for i, p in enumerate(a.record):
        name, _, path = p.rpartition("=") if "=" in p else (Path(p).stem, "", p)
        pid = f"rec-{i + 1}"
        projects.append({"id": pid, "name": name, "role": "record", "records": 1})
        refs[pid] = estimate.learn_from(projects[-1], _load(path))
    rates = estimate.default_rates()
    if a.rates:
        if a.rates.endswith(".json"):
            rates = estimate.load_rates(_load(a.rates))
        else:
            estimate.read_rates(xlsx.read_workbook(a.rates), rates)
    calc = estimate.est_compute(rows, X.get("est") or estimate.new_est(), rates, projects, refs, X.get("bundle"))
    units = "/".join(calc["units"])
    print(f"설비비 {js.fmt_cost(calc['eqTotal'])} {units} · 공사비 {js.fmt_cost(calc['wkTotal'])} {rates.get('currency') or ''} · "
          f"투자비 {js.fmt_cost(calc['eqTotal'] + calc['wkTotal'])} · 실적 {len(calc['refs'])}개")
    if a.json:
        _json(a.json, {"eqTotal": calc["eqTotal"], "wkTotal": calc["wkTotal"], "units": calc["units"],
                       "equipment": [{k: e[k] for k in ("key", "cap", "n", "ratio", "expo", "up", "unitEst", "method", "val", "flags")} | {"tag": e["r"]["tag"], "ref": e["ref"] and e["ref"]["key"]} for e in calc["eqRes"]],
                       "works": calc["works"]})
    if a.xlsx:
        export.estimate_workbook(calc, rates, a.name or Path(a.rows).stem).save(a.xlsx)
        print("Excel:", a.xlsx)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pfdcore", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("equipment", help="PFD PDFs → Equipment List")
    e.add_argument("pdfs", nargs="+")
    e.add_argument("--cost", help="manual equipment list with costs (.xlsx/.csv)")
    e.add_argument("--bundle", help="flow or tab bundle JSON (stream values for the equipment)")
    e.add_argument("--cmaps", action="store_true", help="also read fonts the app cannot (pdf.js without CMap files)")
    e.add_argument("--xlsx", help="write the app's Equipment List workbook")
    e.add_argument("--json", help="write the record's equipment JSON")
    e.set_defaults(fn=cmd_equipment)
    s = sub.add_parser("estimate", help="records → investment estimate")
    s.add_argument("--rows", required=True, help="the estimate project's record JSON")
    s.add_argument("--record", action="append", default=[], help="a recorded project's record JSON (NAME=PATH to name it)")
    s.add_argument("--rates", help="company rates (.xlsx/.csv, or the app's settings-rates JSON)")
    s.add_argument("--name", help="project name for the workbook")
    s.add_argument("--xlsx", help="write the app's estimate workbook")
    s.add_argument("--json", help="write the estimate as JSON")
    s.set_defaults(fn=cmd_estimate)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
