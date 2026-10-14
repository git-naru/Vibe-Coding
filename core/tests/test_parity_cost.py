"""Equipment cost matching: pfdcore against the app's own code (SheetJS 0.18.5 for the workbook)."""
import json

import pytest
from conftest import assert_same, jsq, run_app

from pfdcore import cost, equipment, pdf, xlsx


@pytest.fixture(scope="module")
def rows(work):
    return equipment.build_equipment(pdf.read_pdf(work["pdf"]))["rows"]


def test_cost_list_reading(work):
    app = run_app(f"return parseCostWorkbook(workbook({jsq(work['cost'])}));")
    py = cost.parse_cost_workbook(xlsx.read_workbook(work["cost"]))
    assert_same(app, py, "cost list")
    assert py["unit"] == "USD" and len(py["items"]) == 12


@pytest.mark.parametrize("variant", ["plain", "picks", "ai", "edits", "none-list"])
def test_matching(work, rows, variant):
    lst = cost.parse_cost_workbook(xlsx.read_workbook(work["cost"]))
    C = cost.load_cost_list(None, lst, "eq-cost.xlsx")
    if variant == "picks":
        C["pick"] = {"6": "1000-HX-003", "10": "", "11": "2000-PU-006"}
    if variant == "ai":
        C["ai"] = {"10": ["1000-PU-007"], "7": ["9999-ZZ-001"]}
    if variant == "edits":
        C["edits"] = {"1000-PU-007": 5100, "2000-TK-001": 99000.5, "NOT-A-TAG": 1}
    if variant == "none-list":
        C = {"list": None, "unit": "", "edits": {"1000-TK-001": 1234}, "pick": {}, "ai": {}}
    app = run_app(f"return computeCosts({json.dumps(C)}, {json.dumps(rows)});")
    assert_same(app, cost.compute_costs(C, rows), f"cost matching ({variant})")


def test_claude_pairs_are_checked(work, rows):
    lst = cost.parse_cost_workbook(xlsx.read_workbook(work["cost"]))
    C = cost.load_cost_list(None, lst, "eq-cost.xlsx")
    K = cost.compute_costs(C, rows)
    un, cands = cost.cost_ai_request(K, rows)
    answer = {"pairs": [{"item": un[0]["i"], "keys": [cost.eq_key(cands[0]), "NOPE-1"], "why": "x"},
                        {"item": "999", "keys": [cost.eq_key(cands[1])]}, {"item": un[-1]["i"], "keys": "not a list"}, 7]}
    # the app's own filter (costAi) on the same answer
    app = run_app(f"""
const C = {json.dumps(C)}, rows = {json.dumps(rows)}, K = computeCosts(C, rows);
const un = K.unmatched.slice(0, 200), cands = rows.filter(r => !K.byKey[eqKey(r)]).slice(0, 600);
const r = {json.dumps(answer)}; const ok = new Set(cands.map(eqKey)); let n = 0;
(r && Array.isArray(r.pairs) ? r.pairs : []).forEach(p => {{ const ks = (Array.isArray(p.keys) ? p.keys : []).map(String).filter(k => ok.has(k)); if (ks.length && un.some(it => it.i === +p.item)) {{ C.ai[+p.item] = ks; n++; }} }});
return {{n, ai: C.ai, prompt: costPrompt(un, cands), un: un.map(x => x.i), cands: cands.map(eqKey)}};""")
    n = cost.apply_cost_ai(C, un, cands, answer)
    assert app["n"] == n == 1
    assert_same(app["ai"], C["ai"], "Claude pairs kept")
    assert app["un"] == [x["i"] for x in un] and app["cands"] == [cost.eq_key(r) for r in cands]
    assert app["prompt"] == cost.cost_prompt(un, cands)


@pytest.mark.parametrize("text", ["3200-PU-001/002", "3200-pu-1~3", "WF-6400-FH-003A/B", "3200-PU-001~003, 4100-AG-002A/B",
                                  "1000-TK-001, 1000-TK-002 & 004", "2000-IX-002/003/004", "", "  ", "9999-ZZ-1 ~ 0080"])
def test_tag_helpers(text):
    app = run_app(f"return {{e: expandTags({jsq(text)}), n: normTag({jsq(text)})}};")
    assert app == {"e": cost.expand_tags(text), "n": cost.norm_tag(text)}
