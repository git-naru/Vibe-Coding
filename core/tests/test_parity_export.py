"""The Excel downloads: every sheet and cell of pfdcore's workbooks against the app's (SheetJS) files."""
import base64
import copy
import io
import json

from conftest import assert_same, run_app
from test_parity_estimate import scenario  # noqa: F401  (fixture)
from test_parity_pdf import flow_bundle

from pfdcore import cost, equipment, estimate, export, pdf, xlsx

CAPTURE = """window.claude = {use: async k => k === 'downloads' ? {save: async ({filename, data}) => {
  globalThis.__dl = {filename, data: Buffer.from(typeof data === 'string' ? data : data).toString('base64')}; }} : null};"""


def cells(data):
    wb = xlsx.read_workbook(bytes(data), "x.xlsx")
    out = {}
    for name in wb.sheet_names:
        rows = wb.aoa(name, raw=True)
        out[name] = [r for r in rows if r and r[0] != "만든 때"]   # the time of writing differs by nature
    return out


def saved(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_equipment_download(work):
    rows = equipment.build_equipment(pdf.read_pdf(work["pdf"]))
    b = flow_bundle()
    title = equipment.link_equipment_to_flow(rows["rows"], b["tabs"])
    C = cost.load_cost_list(None, cost.parse_cost_workbook(xlsx.read_workbook(work["cost"])), "eq-cost.xlsx")
    C["edits"] = {"1000-PU-007": 5100}
    C["pick"] = {"6": "1000-HX-003"}
    K = cost.compute_costs(C, rows["rows"])
    app = run_app(CAPTURE + f"""
Object.assign(EQ, {{rows: {json.dumps(rows['rows'])}, refsMissing: {json.dumps(rows['refsMissing'])}, areaNames: {json.dumps(rows['areaNames'])},
  cost: {json.dumps(C)}, mbTitle: {json.dumps(title)}, sample: null}});
EQ.costCalc = computeCosts(); S.files = [{{kind: 'pdf', ok: true, file: {{name: 'pfd.pdf'}}, pages: 3}}]; S.sheets = [{{}}, {{}}, {{}}];
await downloadEquipment(); return globalThis.__dl;""")
    assert app and app["filename"].startswith("equipment-list-")
    py = export.equipment_workbook(rows["rows"], rows["refsMissing"], rows["areaNames"], cost=C, costs=K, mb_title=title,
                                   inputs="pfd.pdf (3장)", vision="0/3장 실행")
    a, p = cells(base64.b64decode(app["data"])), cells(saved(py))
    assert list(a) == list(p) == ["Equipment List", "Summary", "도면 미포함 설비", "설비비 매칭", "작성 기준"]
    assert_same(a, p, "Equipment List workbook")


def test_estimate_download(scenario):  # noqa: F811
    sc = copy.deepcopy(scenario)
    est = estimate.new_est()
    est["methods"] = {"1000-PU-001": "unit"}
    app = run_app(CAPTURE + f"""
P.list = {json.dumps(sc['projects'])}; REF.clear();
const recs = {json.dumps(sc['records'])};
for (const p of P.list) if (recs[p.id]) REF.set(p.id, learnFrom(p, recs[p.id]));
S.project = P.list.find(p => p.role === 'estimate'); S.bundle = {json.dumps(sc['bundle'])};
EQ.rows = {json.dumps(sc['rows'])}; EQ.est = {json.dumps(est)}; Object.assign(RATES, {json.dumps(sc['rates'])});
estCompute(); await downloadEstimate(); return globalThis.__dl;""")
    refs = {p["id"]: estimate.learn_from(p, sc["records"][p["id"]]) for p in sc["projects"] if p["id"] in sc["records"]}
    calc = estimate.est_compute(sc["rows"], est, sc["rates"], sc["projects"], refs, sc["bundle"])
    py = export.estimate_workbook(calc, sc["rates"], "산출 (가상)")
    a, p = cells(base64.b64decode(app["data"])), cells(saved(py))
    assert list(a) == list(p) == ["요약", "설비비", "공사비", "공사물량 근거", "산출 기준"]
    assert_same(a, p, "estimate workbook")


def test_equipment_download_with_layouts(work):
    import fixtures
    from pfdcore import layout
    d = work["dir"]
    shs = pdf.read_pdf(work["pdf"]) + pdf.read_pdf(fixtures.layout_pdf(d / "ga.pdf"), file_id=2)
    proc, lays = layout.split_sheets(shs)
    rows = equipment.build_equipment(proc)
    app = run_app(CAPTURE + f"""
Object.assign(EQ, {{rows: {json.dumps(rows['rows'])}, refsMissing: {json.dumps(rows['refsMissing'])}, areaNames: {json.dumps(rows['areaNames'])}, cost: null, mbTitle: '', sample: null}});
EQ.costCalc = null; S.layouts = {json.dumps(lays)};
S.files = [{{kind: 'pdf', ok: true, file: {{name: 'pfd.pdf'}}, pages: 3}}]; S.sheets = [{{}}, {{}}, {{}}];
await downloadEquipment(); return globalThis.__dl;""")
    py = export.equipment_workbook(rows["rows"], rows["refsMissing"], rows["areaNames"], inputs="pfd.pdf (3장)", vision="0/3장 실행", layouts=lays)
    a, p = cells(base64.b64decode(app["data"])), cells(saved(py))
    assert "Layout 위치" in a["Equipment List"][0]
    assert_same(a, p, "Equipment List workbook with Layout")
