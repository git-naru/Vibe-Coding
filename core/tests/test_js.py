"""The JavaScript behaviour pfdcore reproduces, checked against Node (the same V8 + ICU family as the browser)."""
import json

from conftest import run_app

from pfdcore import js, ssf

NUMS = [0, -0.0, 1, -1, 0.5, 1.005, 2.675, 1234.565, -0.001, 0.125, 1 / 3, 2 / 3, 1e21, 1e-7, 123e-20, 2**53 + 2, 123456789.125,
        99.995, 0.1 + 0.2, 5e-324, 1.7976931348623157e308, 47.9, 52.0, 1150.25, 100, 99.99999]
STRS = ["5.", ".5", " 12 ", "1.2.3", "-.5", "--1", "", "  ", "0x1A", "1e5", "Infinity", "-0", "1,000", "12abc", " 12　"]
SORT = ["6400-FH-003", "(Tag 없음)", "WF-6400-FH-003", "6400-FH-003A", "", "_a", "-a", "a", "B", "b", "가", "1", "3200", "0900", "A-1", "A1", "a b"]


def test_numbers_to_text():
    app = run_app(f"const xs = {json.dumps(NUMS)}; return xs.map(x => [String(x), fmt(x), fmtCost(x), x.toFixed(2), x.toFixed(0), Math.round(x), x.toPrecision(6), x.toExponential(3)]);")
    for x, a in zip(NUMS, app):
        assert a == [js.num_str(x), js.fmt(x), js.fmt_cost(x), js.to_fixed(x, 2), js.to_fixed(x, 0), js.plain(js.js_round(x)),
                     ssf.to_precision(x, 6), ssf.to_exponential(x, 3)], x


def test_text_to_numbers():
    app = run_app(f"return {json.dumps(STRS)}.map(s => [Number(s), parseFloat(s), s.trim()]);")
    for s, a in zip(STRS, app):
        assert js.plain([js.number(s), js.parse_float(s), js.trim(s)]) == a, s


def test_locale_sort_and_keys():
    app = run_app(f"return {{s: {json.dumps(SORT)}.slice().sort((a, b) => a.localeCompare(b)), k: Object.keys({{b: 1, 10: 1, 2: 1, a: 1, '01': 1, '4294967295': 1, '7': 1}})}};")
    assert js.sort(SORT, js.locale_compare) == app["s"]
    assert js.keys({"b": 1, "10": 1, "2": 1, "a": 1, "01": 1, "4294967295": 1, "7": 1}) == app["k"]


def test_regex_semantics():
    cases = [(r"\bTANK\b", "급수TANK"), (r"^\d+$", "１２"), (r"^a$", "a\n"), (r"\s", " "), (r"\s", "\x1c"), (r"^.$", "\r")]
    app = run_app(f"return {json.dumps(cases)}.map(([p, s]) => new RegExp(p).test(s));")
    assert [js.test(p, s) for p, s in cases] == app
