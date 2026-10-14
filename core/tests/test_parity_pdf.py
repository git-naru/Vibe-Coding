"""PDF reading, sheet links and the Equipment List: pfdcore against the app's own code (pdf.js 3.11.174)."""
import json

import pytest
from conftest import assert_same, jsq, run_app

from pfdcore import equipment, pdf, sheets

SHEET_KEYS = ["key", "fileId", "file", "page", "dwg", "aliases", "title", "connectors", "badges", "items", "imgs",
              "textLayer", "textTable", "rotate", "grid", "area", "eq", "layTitle"]


@pytest.fixture(scope="module")
def app_pdf(work):
    return run_app(f"""
const e = fileEntry({jsq(work['pdf'])}); S.files = [e]; await readPdf(e);
const links = buildLinks(S.sheets); buildEquipment();
return {{sheets: S.sheets.map(s => Object.fromEntries({json.dumps(SHEET_KEYS)}.map(k => [k, s[k]]))),
        links: {{flows: links.flows, missing: links.missing, matched: links.matched, issues: links.issues, missingCount: links.missingCount}},
        eq: {{rows: EQ.rows, refsMissing: EQ.refsMissing, areaNames: EQ.areaNames}}}};""")


@pytest.fixture(scope="module")
def py_pdf(work):
    shs = pdf.read_pdf(work["pdf"])
    return shs, sheets.build_links(shs), equipment.build_equipment(shs)


def test_text_items_and_images(app_pdf, py_pdf):
    shs, _, _ = py_pdf
    assert len(app_pdf["sheets"]) == len(shs) == 3
    for a, b in zip(app_pdf["sheets"], shs):
        assert b["warnings"] == []
        assert_same(a["items"], b["items"], f"{a['key']} text items")
        assert_same(a["imgs"], b["imgs"], f"{a['key']} image boxes")
        assert a["rotate"] == b["rotate"]


def test_sheet_records(app_pdf, py_pdf):
    shs, _, _ = py_pdf
    for a, b in zip(app_pdf["sheets"], shs):
        assert_same(a, {k: b.get(k) for k in SHEET_KEYS}, f"{a['key']} sheet")


def test_links(app_pdf, py_pdf):
    _, links, _ = py_pdf
    assert_same(app_pdf["links"], links, "sheet links")
    assert links["missingCount"] >= 1   # the fixture cites drawings that are not in the input


def test_equipment_list(app_pdf, py_pdf):
    _, _, eq = py_pdf
    assert_same(app_pdf["eq"], eq, "Equipment List")
    tags = [r["tag"] for r in eq["rows"]]
    assert "1000-PU-002" in tags and "(Tag 없음)" in tags and eq["refsMissing"]


def flow_bundle():
    """A made-up two-tab flow: streams with values and the equipment tags at their ends."""
    v = lambda dm, nm, dx, T, P: {"dm": dm, "nm": nm, "dxm": dx, "T": T, "P": P, "rho": "1.18"}
    main = {"meta": {"title": "Brine", "main": True}, "categories": {"brine": {"label": "Brine"}, "slurry": {"label": "Lime slurry"}},
            "streams": {"105": {"from": "1000-HX-003", "to": "2000-TK-001", "cat": "brine", "v": v("1,150", "47.9", "52.0", "60", "3.8")},
                        "101": {"from": "1000-TK-001", "to": "1000-PU-001/002", "cat": "brine", "v": v("1,200", "50.0", "55.0", "25", "1.0")},
                        "102": {"from": "1000-PU-001/002", "to": "1000-HX-003", "cat": "brine", "v": v("1,180", "49.2", "", "25", "4.5")},
                        "110": {"from": "1000-TK-004", "to": "1000-HX-003", "cat": "slurry", "v": v("40", "1.7", "2.0", "30", "3.0")},
                        "999": {"from": "1000-TK-004", "to": "1000-PU-007"}},
            "edges": [{"id": "120", "from": "1000-FL-005", "to": "WF-1000-FA-002"}],
            "nodes": [{"id": "1000-TK-001"}, {"id": "P-BOX", "sub": "1000-PU-001/002"}],
            "packages": [{"id": "P1", "name": "Feed 패키지", "members": ["1000-TK-001", "P-BOX"]}, {"id": "P2", "name": "Softening", "members": ["1000-HX-003"]}]}
    side = {"meta": {"title": "Utility"}, "streams": {"201": {"from": "2000-PU-005", "to": "2000-IX-002", "v": {"dm": "300", "nm": "12.5"}}}}
    return {"kind": "bundle", "title": "Made-up plant", "tabs": [{"key": "main", "label": "Main Stream", "main": True, "flow": main},
                                                               {"key": "u", "label": "Utility", "flow": side}]}


def test_stream_values_on_equipment(app_pdf, py_pdf):
    _, _, eq = py_pdf
    rows = json.loads(json.dumps(eq["rows"]))
    b = flow_bundle()
    app = run_app(f"EQ.rows = {json.dumps(rows)}; S.bundle = {json.dumps(b)}; linkEquipmentToFlow(); return {{rows: EQ.rows, title: EQ.mbTitle}};")
    title = equipment.link_equipment_to_flow(rows, b["tabs"])
    assert_same(app["rows"], rows, "rows with stream values")
    assert app["title"] == title
    assert sum(1 for r in rows if r.get("mb")) >= 4


@pytest.mark.parametrize("mode", ["app", "read"])
def test_fonts_needing_cmap_files(tmp_path, mode):
    """The app gives pdf.js no cMapUrl, so these fonts' text is dropped; "read" is what a fixed app would see."""
    import fixtures
    p = fixtures.cjk_pdf(tmp_path / "cjk.pdf")
    app = run_app(("withCMaps(); " if mode == "read" else "") + f"const e = fileEntry({jsq(p)}); await readPdf(e); return S.sheets.map(s => s.items);")
    py = pdf.read_pdf(p, cmap_fonts=mode)
    assert_same(app, [s["items"] for s in py], f"items ({mode})")
    korean = [it["s"] for it in py[0]["items"] if any(ord(c) > 0x3000 for c in it["s"])]
    assert korean == ([] if mode == "app" else ["급수탱크", "보일러"])
    assert py[0]["warnings"] == (["cmap-font"] if mode == "app" else [])


@pytest.fixture(scope="module")
def layout_files(work):
    import fixtures
    d = work["dir"]
    return [str(work["pdf"]), str(fixtures.layout_pdf(d / "unit-1000-ga.pdf")), str(fixtures.layout_pdf(d / "plant-layout.pdf", title=False))]


def _read_all(files, roles=None):
    from pfdcore import layout
    shs = []
    for i, f in enumerate(files):
        shs.extend(pdf.read_pdf(f, file_id=i + 1))
    return layout.split_sheets(shs, roles)


@pytest.mark.parametrize("switch", [None, 1, 2])
def test_layout_sheets(layout_files, switch):
    """Layout/GA sheets go beside the list; their tags point at its rows. switch = the file the viewer flips."""
    from pfdcore import layout
    app = run_app(f"""
const files = {json.dumps(layout_files)};
for (let i = 0; i < files.length; i++) {{ const e = fileEntry(files[i], i + 1); S.files.push(e); await readPdf(e); e.status = '완료'; }}
buildEquipment();
{f"setFileRole({switch});" if switch else ""}
const LX = layoutIndex();
return {{sheets: S.sheets.map(s => s.key), layouts: S.layouts.map(s => ({{key: s.key, layTitle: s.layTitle}})), rows: EQ.rows,
        idx: {{sheets: LX.sheets.map(L => ({{key: L.sh.key, marks: L.marks}})), rowsOf: LX.rowsOf, where: LX.where}},
        at: EQ.rows.map(r => {{ const w = !r.untagged && LX.where.get(normTag(r.tag)); return w ? w.map(j => layoutLabel(LX.sheets[j].sh)).join(', ') : ''; }})}};""")
    names = {1: "pfd.pdf", 2: "unit-1000-ga.pdf"}
    roles = {names[switch]: "pfd" if switch == 2 else "layout"} if switch else None
    proc, lays = _read_all(layout_files, roles)
    eq = equipment.build_equipment(proc)
    LX = layout.layout_index(eq["rows"], lays)
    py = {"sheets": [s["key"] for s in proc], "layouts": [{"key": s["key"], "layTitle": s["layTitle"]} for s in lays], "rows": eq["rows"],
          "idx": {"sheets": [{"key": L["sh"]["key"], "marks": L["marks"]} for L in LX["sheets"]], "rowsOf": LX["rowsOf"], "where": LX["where"]},
          "at": [layout.layout_at(LX, r) for r in eq["rows"]]}
    assert_same(app, py, f"Layout sheets (switch {switch})")
    if switch is None:
        assert [s["key"] for s in lays] == ["unit-1000-ga.pdf p1", "plant-layout.pdf p1"]
        assert {m["how"] for L in LX["sheets"] for m in L["marks"]} == {"tag", "short"}
