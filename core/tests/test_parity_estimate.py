"""Construction quantities, rates, learning from records and the investment estimate: pfdcore against the app."""
import copy
import json

import pytest
from conftest import assert_same, jsq, run_app
from test_parity_pdf import flow_bundle

from pfdcore import cost, equipment, estimate, pdf, xlsx


def test_quantity_list(work):
    prev = {"file": "", "items": [{"target": "공통", "work": "가설", "qty": 1, "unit": "식", "manual": True}, {"target": "x", "work": "old", "qty": 2, "unit": "m"}]}
    app = run_app(f"EQ.qty = {json.dumps(prev)}; await readQtyFile(fileEntry({jsq(work['qty'])}).file); return EQ.qty;")
    py, _ = estimate.read_qty(xlsx.read_workbook(work["qty"]), copy.deepcopy(prev), "qty.xlsx")
    assert_same(app, py, "quantity list")


def test_rate_list(work):
    start = {"items": [{"work": "배관", "unit": "m", "rate": 999}, {"work": "100", "unit": "식", "rate": 5}], "currency": "", "exps": dict(estimate.EXP_DEFAULT), "qexp": 0.7}
    app = run_app(f"Object.assign(RATES, {json.dumps(start)}); await readRateFile(fileEntry({jsq(work['rates'])}).file); return RATES;")
    py = copy.deepcopy(start)
    estimate.read_rates(xlsx.read_workbook(work["rates"]), py)
    assert_same(app, py, "rates")
    assert py["currency"] == "USD"


@pytest.mark.parametrize("text", ["1000-PU-001~002", "공통", "", "Feed 패키지", "feed package", "9999-XX-001", "1000-PU-001A", "SOFTENING 설비"])
def test_quantity_targets(work, text):
    rows = equipment.build_equipment(pdf.read_pdf(work["pdf"]))["rows"]
    keys = [cost.eq_key(r) for r in rows if not r.get("untagged")]
    pk = estimate.bundle_packages(flow_bundle())
    app = run_app(f"return resolveTarget({jsq(text)}, new Set({json.dumps(keys)}), {json.dumps(pk)});")
    assert_same(app, estimate.resolve_target(text, keys, pk), f"target {text!r}")


def scaled(rows, k):
    """The same plant at another size: vessel volumes and stream flows × k."""
    out = copy.deepcopy(rows)
    for r in out:
        if isinstance(r.get("vol"), (int, float)):
            r["vol"] = r["vol"] * k
        mb = r.get("mb")
        if mb:
            for f in ("dm", "nm", "dx"):
                if isinstance(mb.get(f), (int, float)):
                    mb[f] = round(mb[f] * k, 3)
    return out


@pytest.fixture(scope="module")
def scenario(work):
    """Two made-up recorded projects and one estimate project."""
    rows = equipment.build_equipment(pdf.read_pdf(work["pdf"]))["rows"]
    b = flow_bundle()
    equipment.link_equipment_to_flow(rows, b["tabs"])
    lst = cost.parse_cost_workbook(xlsx.read_workbook(work["cost"]))
    qty, _ = estimate.read_qty(xlsx.read_workbook(work["qty"]), None, "qty.xlsx")
    rec_a = {"bundle": b, "equipment": {"rows": rows, "cost": cost.load_cost_list(None, lst, "eq-cost.xlsx")}, "qty": qty}
    b2 = copy.deepcopy(b)
    b2["tabs"][0]["flow"]["packages"][0]["name"] = "Brine Feed Package"
    rows_b = scaled(rows, 0.5)
    cost_b = cost.load_cost_list(None, lst, "eq-cost-b.xlsx")
    cost_b["edits"] = {"1000-TK-001": 80000, "1000-HX-003": 30000, "2000-TK-001": 50000}
    rec_b = {"bundle": b2, "equipment": {"rows": rows_b, "cost": cost_b},
             "qty": {"file": "", "items": [{"target": "1000-TK-001", "work": "기초 콘크리트", "qty": 18, "unit": "m³"},
                                           {"target": "Brine Feed Package", "work": "철골", "qty": 7, "unit": "t"},
                                           {"target": "", "work": "토목", "qty": 260, "unit": "m³"},
                                           {"target": "1000-PU-001/002", "work": "배관", "qty": 70, "unit": "m"}]}}
    projects = [{"id": "proj-a", "name": "실적 A (가상)", "role": "record", "records": 1},
                {"id": "proj-b", "name": "실적 B (가상)", "role": "record", "records": 2},
                {"id": "proj-empty", "name": "기록 없음", "role": "record", "records": 0},
                {"id": "proj-est", "name": "산출 (가상)", "role": "estimate", "records": 1}]
    rates = estimate.default_rates()
    estimate.read_rates(xlsx.read_workbook(work["rates"]), rates)
    rates["exps"]["펌프"] = 0.55
    new_rows = scaled(rows, 2)
    return {"projects": projects, "records": {"proj-a": rec_a, "proj-b": rec_b}, "rows": new_rows, "bundle": b, "rates": rates}


@pytest.mark.parametrize("variant", ["learn-all", "choices", "only-b", "no-refs", "qexp"])
def test_estimate(scenario, variant):
    sc = copy.deepcopy(scenario)
    est = estimate.new_est()
    if variant == "choices":
        est.update({"caps": {"1000-TK-001": {"v": 40, "u": "m³"}}, "methods": {"1000-PU-001": "unit", "1000-HX-003": "skip"},
                    "over": {"1000-TK-004": 77000}, "qover": {"토목": 650, "전기 케이블": 1500}})
    if variant == "only-b":
        est["refs"] = ["proj-b"]
    if variant == "no-refs":
        est["refs"] = []
    if variant == "qexp":
        sc["rates"]["qexp"] = 0.85
    app = run_app(f"""
P.list = {json.dumps(sc['projects'])}; REF.clear();
const recs = {json.dumps(sc['records'])};
for (const p of P.list) if (recs[p.id]) REF.set(p.id, learnFrom(p, recs[p.id]));
S.project = P.list.find(p => p.role === 'estimate'); S.bundle = {json.dumps(sc['bundle'])};
EQ.rows = {json.dumps(sc['rows'])}; EQ.est = {json.dumps(est)}; Object.assign(RATES, {json.dumps(sc['rates'])});
estCompute(); return EST_CALC;""")
    refs = {p["id"]: estimate.learn_from(p, sc["records"][p["id"]]) for p in sc["projects"] if p["id"] in sc["records"]}
    py = estimate.est_compute(sc["rows"], est, sc["rates"], sc["projects"], refs, sc["bundle"])
    assert_same(app, py, f"estimate ({variant})")
    if variant == "learn-all":
        assert py["eqTotal"] > 0 and py["wkTotal"] > 0 and any(w["pkg"] for w in py["works"]) and any(w["eq"] for w in py["works"])
