"""Construction quantities (records) and investment estimate (app.html section 12).

Records carry actual construction quantities per equipment (tag), per package or for the whole project ("공통").
An estimate takes equipment cost from the most similar recorded equipment of the same kind, scaled by
capacity ratio ^ exponent (or the recorded unit price × capacity); construction cost = learned quantities ×
company rates.

State shapes follow the app's records (see data-schema.md): rows = Equipment List rows, `est` = the estimate
choices {refs, caps, methods, over, qover}, `rates` = {items, currency, exps, qexp}.
"""
import math

from . import js
from .cost import compute_costs, cost_num, eq_key, expand_tags, jacc, name_tokens, norm_tag
from .equipment import stream_tags

EXP_DEFAULT = {"펌프": 0.52, "탱크": 0.57, "열교환기": 0.6, "반응조": 0.54, "교반기": 0.5, "필터": 0.6, "팬·블로어": 0.6, "압축기": 0.75, "보일러": 0.7, "건조기": 0.6,
               "시크너·청징조": 0.6, "이온교환탑": 0.6, "믹서": 0.5, "컨베이어": 0.65, "빈·호퍼": 0.6, "폰드": 0.8, "_기본": 0.6}
VOL_KINDS = {"탱크", "반응조", "시크너·청징조", "빈·호퍼", "폰드", "공기 저장조", "믹서", "스크러버"}
PKG_STOP = {"패키지", "PACKAGE", "PKG", "설비", "계통", "SYSTEM", "UNIT", "공정", "PLANT"}
QCOL = {"target": (r"tag|대상|패키지|package|설비|equip", "i"), "work": (r"공종|work|trade|discipline|항목|구분", "i"),
        "qty": (r"물량|수량|q'?ty|quantity|amount", "i"), "unit": (r"단위|unit|uom", "i")}
RATE_COLS = {"work": QCOL["work"], "unit": QCOL["unit"], "rate": (r"단가|rate|unit\s*(price|cost)|price", "i")}


def default_rates():
    return {"items": [], "currency": "", "exps": dict(EXP_DEFAULT), "qexp": 0.7}


def load_rates(d):
    """The `settings-rates` document as the app loads it over its defaults."""
    r = default_rates()
    if d:
        r.update({"items": d.get("items") or [], "currency": d.get("currency") or "", "exps": {**EXP_DEFAULT, **(d.get("exps") or {})},
                  "qexp": 0.7 if d.get("qexp") is None else d["qexp"]})
    return r


def norm_name(s):
    return js.trim(js.sub(r"\s+", " ", (js.jstr(s) if js.truthy(s) else "").upper()))


def pkg_tokens(s):
    return {t: True for t in name_tokens(s) if t not in PKG_STOP}


def pkg_sim(a, b):
    return 1 if norm_name(a) == norm_name(b) else jacc(pkg_tokens(a), pkg_tokens(b))


def _pos(x):
    return js.is_num(x) and x > 0


def cap_of(r):
    """Capacity of an equipment row: vessels by nominal volume, the rest by design (else nominal) flow."""
    vol = cost_num(r.get("vol"))
    mb = r.get("mb")
    flow = None
    if mb:
        flow = cost_num(mb.get("dx"))
        if not js.truthy(flow):
            flow = cost_num(mb.get("nm"))
    if r.get("kind") in VOL_KINDS and _pos(vol):
        return {"v": vol, "u": "m³"}
    if _pos(flow):
        return {"v": flow, "u": "t/h"}
    if _pos(vol):
        return {"v": vol, "u": "m³"}
    return None


def fmt_cap(c):
    return f"{js.fmt(c['v'])} {c['u']}" if c else "–"


def bundle_packages(B):
    """Packages of a flow bundle with their equipment keys (box id is a tag, or tags in the box subtitle)."""
    out = []
    for t in (B or {}).get("tabs") or []:
        F = t.get("flow") or {}
        by_id = {}
        for n in F.get("nodes") or []:
            by_id[js.jstr(n.get("id"))] = n
        for p in F.get("packages") or []:
            keys = js.unique(norm_tag(x) for m in p["members"] for n in [by_id.get(js.jstr(m)) or {"id": m}]
                             for x in [*stream_tags(n.get("id")), *stream_tags(n.get("sub") or "")])
            out.append({"name": p.get("name"), "keys": keys, "tab": t.get("label")})
    return out


def resolve_target(text, key_set, pkgs):
    """Where a quantity row belongs: equipment tags, a package, or the whole project."""
    keys = list(dict.fromkeys(key_set))
    have = set(keys)
    s = js.trim(js.jstr(text) if js.truthy(text) else "")
    if not s or js.test(r"^(공통|전체|common|general|project|프로젝트|기타)$", s, "i"):
        return {"scope": "common"}
    tags = expand_tags(s)
    if tags:
        ks = js.unique(k for t in tags for k in ([t] if t in have else [k for k in keys if js.sub("[A-Z]$", "", k, count=1) == t or k == js.sub("[A-Z]$", "", t, count=1)]))
        return {"scope": "eq", "keys": ks} if ks else {"scope": "none", "why": "Equipment List에 없는 Tag (공통으로 셈)"}
    sc = js.sort([[x, pkg_sim(s, x["name"])] for x in pkgs if pkg_sim(s, x["name"]) >= 0.5], lambda a, b: b[1] - a[1])
    return {"scope": "pkg", "pkg": sc[0][0]["name"]} if sc else {"scope": "none", "why": "대상을 찾지 못함 (공통으로 셈)"}


# ---- reading quantity and rate lists -----------------------------------------------------------
def parse_table(wb, rx, need):
    """First sheet row that names the needed columns → the rows below it."""
    for sn in wb.sheet_names:
        A = wb.aoa(sn, raw=True)
        for h in range(min(40, len(A))):
            row = [js.trim(js.jstr(c)) for c in A[h]]
            cols = {}
            for j, c in enumerate(row):
                if not c:
                    continue
                for k, (src, fl) in rx.items():
                    if cols.get(k) is None and js.test(src, c, fl):
                        cols[k] = j
                        break
            if not all(cols.get(k) is not None for k in need):
                continue
            return {"sheet": sn, "headerRow": h + 1, "cols": cols, "rows": [{"x": x, "row": h + 2 + i} for i, x in enumerate(A[h + 1:])],
                    "header": A[h]}
    return None


def _cell(x, j):
    return x[j] if j is not None and 0 <= j < len(x) else None


def read_qty(wb, prev=None, file=""):
    """A construction-quantity list → the record's `qty` (manually added rows of `prev` are kept).
    Returns (qty, table) or (None, None) when no header with 공종 and 물량 is found."""
    T = parse_table(wb, QCOL, ["work", "qty"])
    if not T:
        return None, None
    c = T["cols"]
    items = []
    for r in T["rows"]:
        x = r["x"]
        it = {"target": js.trim(js.jstr(_cell(x, c.get("target")))) if c.get("target") is not None else "",
              "work": js.trim(js.jstr(_cell(x, c["work"]))), "qty": cost_num(_cell(x, c["qty"])),
              "unit": js.trim(js.jstr(_cell(x, c.get("unit")))) if c.get("unit") is not None else "", "row": r["row"]}
        if it["work"] and it["qty"] is not None and not js.test(r"합\s*계|소\s*계|total", it["work"], "i"):
            items.append(it)
    kept = [it for it in ((prev or {}).get("items") or []) if it.get("manual")]
    return {"file": file, "items": [*kept, *items]}, T


def add_qty_row(qty, rates, target, work, q, unit=""):
    """A row typed into the quantity card (unit defaults to the rate's unit for that work)."""
    qty = qty or {"file": "", "items": []}
    rt = next((r for r in rates["items"] if norm_name(r["work"]) == norm_name(work)), None)
    qty["items"].append({"target": js.trim(target), "work": work, "qty": q, "unit": js.trim(unit) or (rt or {}).get("unit") or "", "manual": True})
    return qty


def read_rates(wb, rates):
    """A company rate list merged into `rates` (the same work replaced); returns the number of rows read, or None."""
    T = parse_table(wb, RATE_COLS, ["work", "rate"])
    if not T:
        return None
    c = T["cols"]
    items = [{"work": js.trim(js.jstr(_cell(r["x"], c["work"]))), "unit": js.trim(js.jstr(_cell(r["x"], c.get("unit")))) if c.get("unit") is not None else "",
              "rate": cost_num(_cell(r["x"], c["rate"]))} for r in T["rows"]]
    items = [r for r in items if r["work"] and r["rate"] is not None]
    by = {norm_name(r["work"]): r for r in rates["items"]}
    for r in items:
        by[norm_name(r["work"])] = r
    rates["items"] = js.values(by)
    h = _cell(T["header"], c["rate"])
    h = js.jstr(h) if js.truthy(h) else ""
    if not rates.get("currency"):
        m = js.match(r"\(([^)]+)\)", h)
        rates["currency"] = js.trim((m.group(1) if m else None) or "")
    return len(items)


# ---- learning data from recorded projects ------------------------------------------------------
def learn_from(p, X):
    """What one recorded project teaches (its latest record's JSON `X`)."""
    E = X.get("equipment") or {}
    rows = E.get("rows") or []
    K = compute_costs(E["cost"], rows) if E.get("cost") else None
    eqs = []
    for r in rows:
        if r.get("untagged"):
            continue
        k = eq_key(r)
        b = K and K["byKey"].get(k)
        eqs.append({"proj": p.get("id"), "projName": p.get("name"), "key": k, "tag": r["tag"], "name": r["name"], "kind": r["kind"], "cap": cap_of(r), "cost": b["cost"] if b else None})
    by_key = {e["key"]: e for e in eqs}
    total = js.add((e["cost"] if js.truthy(e["cost"]) else 0) for e in eqs)
    pk = [{**x, "cost": js.add(((by_key.get(k) or {}).get("cost") or 0) for k in x["keys"])} for x in bundle_packages(X.get("bundle"))]
    key_set = [e["key"] for e in eqs]
    qty = [{**it, **resolve_target(it.get("target"), key_set, pk)} for it in ((X.get("qty") or {}).get("items") or [])]
    return {"p": p, "unit": ((E.get("cost") or {}).get("unit")) or "", "eqs": eqs, "byKey": by_key, "total": total, "pk": pk, "qty": qty,
            "withCost": sum(1 for e in eqs if _pos(e["cost"]))}


# ---- estimate ----------------------------------------------------------------------------------
def new_est():
    return {"refs": None, "caps": {}, "methods": {}, "over": {}, "qover": {}}


def est_equipment(rows, est, rates, refs):
    X = rates["exps"]
    pool = [e for d in refs for e in d["eqs"] if _pos(e["cost"])]
    out = []
    for r in rows:
        key = eq_key(r)
        cap = est["caps"].get(key) or cap_of(r)
        n = X.get(r["kind"])
        if n is None:
            n = X.get("_기본")
        if n is None:
            n = 0.6
        t = name_tokens(r["name"])
        same = [e for e in pool if e["kind"] == r["kind"]]

        def sim(e):
            return jacc(t, name_tokens(e["name"]))
        sized = [e for e in same if e["cap"] and e["cap"]["u"] == cap["u"]] if cap else []
        if sized:
            ref = js.sort(sized, lambda a, b: (abs(math.log(cap["v"] / a["cap"]["v"])) - abs(math.log(cap["v"] / b["cap"]["v"])))
                          or ((b["key"] == key) - (a["key"] == key)) or (sim(b) - sim(a)))[0]
        else:
            s = js.sort(same, lambda a, b: ((b["key"] == key) - (a["key"] == key)) or (sim(b) - sim(a)))
            ref = s[0] if s else None
        ratio = cap["v"] / ref["cap"]["v"] if ref and cap and ref["cap"] and ref["cap"]["u"] == cap["u"] else None
        expo = ref["cost"] * (math.pow(ratio, n) if ratio else 1) if ref else None
        up = js.median([e["cost"] / e["cap"]["v"] for e in sized])
        unit_est = up * cap["v"] if up is not None and cap else None
        method = est["methods"].get(key) or ("skip" if r.get("untagged") else "expo" if expo is not None else "none")
        over = est["over"].get(key)
        val = None if method == "skip" else over if over is not None else expo if method == "expo" else unit_est if method == "unit" else None
        flags = []
        if not r.get("untagged") and not same:
            flags.append("같은 종류 실적 설비비 없음")
        if ref and not ratio:
            flags.append("같은 단위 용량 실적 없음 — 실적 금액 그대로" if cap else "용량 정보 없음 — 실적 금액 그대로")
        if ratio and (ratio > 3 or ratio < 1 / 3):
            flags.append(f"용량 차이 큼 (×{js.fmt(js.js_round(ratio * 100) / 100)})")
        if method == "unit" and unit_est is None:
            flags.append("단가 산출 불가 (용량 필요)")
        out.append({"r": r, "key": key, "cap": cap, "n": n, "ref": ref, "ratio": ratio, "expo": expo, "up": up, "upN": len(sized), "unitEst": unit_est,
                    "method": method, "val": val, "over": over is not None, "flags": flags})
    return out


def est_quantities(eq_res, refs, rates, bundle):
    m = 0.7 if rates.get("qexp") is None else rates["qexp"]
    W = {}
    eq_by = {e["key"]: e for e in eq_res}

    def add(work, unit, part, q, why):
        k = norm_name(work)
        w = W.get(k)
        if w is None:
            w = W[k] = {"work": work, "unit": unit, "eq": 0, "pkg": 0, "common": 0, "lines": []}
        w[part] += q
        if not js.truthy(w["unit"]) and js.truthy(unit):
            w["unit"] = unit
        w["lines"].append({"part": part, "q": q, "why": why})

    def scale(v_new, v_ref):
        return math.pow(v_new / v_ref, m) if _pos(v_new) and _pos(v_ref) else 1

    # equipment-level quantities, learned per equipment kind: recorded quantity / Σ cost^m of that kind's priced
    # equipment in the record, applied to Σ cost^m of the new equipment of the kind (one value per record, averaged)
    new_by = {}
    for e in eq_res:
        if e["method"] != "skip" and _pos(e["val"]):
            new_by.setdefault(e["r"]["kind"], []).append(e)
    acc = {}
    for d in refs:
        qk = {}
        for x in d["qty"]:
            if x.get("scope") != "eq":
                continue
            for k in x["keys"]:
                e = d["byKey"].get(k)
                if not e:
                    continue
                kk = js.jstr(e["kind"]) + "|" + norm_name(x["work"])
                v = qk.get(kk)
                if v is None:
                    v = qk[kk] = {"kind": e["kind"], "work": x["work"], "unit": x.get("unit"), "q": 0}
                v["q"] += x["qty"] / len(x["keys"])
        for kk, v in js.entries(qk):
            ns = new_by.get(v["kind"]) or []
            priced = [e for e in d["eqs"] if e["kind"] == v["kind"] and _pos(e["cost"])]
            ref_b = js.add(math.pow(e["cost"], m) for e in priced)
            if not ns or not ref_b > 0:
                continue
            new_b = js.add(math.pow(e["val"], m) for e in ns)
            a = acc.get(kk)
            if a is None:
                a = acc[kk] = {**v, "n": len(ns), "xs": []}
            a["xs"].append({"q": v["q"] * new_b / ref_b, "why": f"{js.jstr(d['p'].get('name'))} {js.jstr(v['kind'])} {len(priced)}기 {js.fmt(js.js_round(v['q'] * 100) / 100)}{js.jstr(v['unit'])}"})
    for a in js.values(acc):
        add(a["work"], a["unit"], "eq", js.mean([x["q"] for x in a["xs"]]), f"{js.jstr(a['kind'])} {a['n']}기 ← {', '.join(x['why'] for x in a['xs'])}")
    # package-level quantities: most similar recorded package name, scaled by package equipment cost
    new_pk = [{**p, "cost": js.add(((eq_by.get(k) or {}).get("val") or 0) for k in p["keys"])} for p in bundle_packages(bundle)]
    rp = [{**x, "pk": next((p for p in d["pk"] if p["name"] == x.get("pkg")), None), "d": d} for d in refs for x in d["qty"] if x.get("scope") == "pkg"]
    pkg_unused = len(rp) and not new_pk
    for P2 in new_pk:
        by = {}
        kinds = dict.fromkeys(k for k in ((eq_by.get(k) or {"r": {}})["r"].get("kind") for k in P2["keys"]) if js.truthy(k))
        for x in rp:
            j = max(pkg_sim(P2["name"], x.get("pkg")),
                    0.8 * jacc(kinds, dict.fromkeys(k for k in ((x["d"]["byKey"].get(k) or {}).get("kind") for k in x["pk"]["keys"]) if js.truthy(k))) if x["pk"] else 0)
            if j >= 0.5:
                by.setdefault(norm_name(x["work"]), []).append({**x, "j": j})
        for xs in js.values(by):
            best = max(x["j"] for x in xs)
            top = [x for x in xs if x["j"] == best]
            rr = [P2["cost"] / x["pk"]["cost"] if x["pk"] and _pos(x["pk"]["cost"]) and _pos(P2["cost"]) else 1 for x in top]
            big = any(r > 3 or r < 1 / 3 for r in rr)
            add(xs[0]["work"], xs[0].get("unit"), "pkg", js.mean([x["qty"] * scale(P2["cost"], x["pk"] and x["pk"]["cost"]) for x in top]),
                f"{js.jstr(P2['name'])} ← {', '.join(js.jstr(x.get('pkg')) + '@' + js.jstr(x['d']['p'].get('name')) for x in top)} "
                f"(설비비 비 ×{'/'.join(js.fmt(js.js_round(r * 100) / 100) for r in rr)}{' · 규모 차이 큼 — 확인' if big else ''})")
    # project-wide quantities: average intensity per unit of equipment cost
    total_new = js.add((e["val"] if js.truthy(e["val"]) else 0) for e in eq_res)
    cw = {}
    for d in refs:
        if not _pos(d["total"]):
            continue
        s = {}
        for x in d["qty"]:
            if x.get("scope") not in ("common", "none"):
                continue
            k = norm_name(x["work"])
            if k not in s:
                s[k] = {"work": x["work"], "unit": x.get("unit"), "q": 0}
            s[k]["q"] += x["qty"]
        for k, v in js.entries(s):
            c = cw.get(k)
            if c is None:
                c = cw[k] = {"work": v["work"], "unit": v["unit"], "xs": []}
            c["xs"].append({"i": v["q"] / d["total"], "name": d["p"].get("name")})
    for c in js.values(cw):
        add(c["work"], c["unit"], "common", js.mean([x["i"] for x in c["xs"]]) * total_new, f"설비비 합계 × 실적 원단위 ({', '.join(js.jstr(x['name']) for x in c['xs'])})")
    return {"W": W, "totalNew": total_new, "pkgUnused": pkg_unused, "newPk": new_pk}


def _and(*xs):
    """a && b && c: the first falsy operand, else the last."""
    for x in xs[:-1]:
        if not js.truthy(x):
            return x
    return xs[-1]


def est_compute(rows, est, rates, projects, refs_by_id, bundle):
    """The estimate (the app's EST_CALC). projects = the project list (id, name, role, records);
    refs_by_id[project id] = learn_from(...) of its latest record, or None."""
    est = est or new_est()
    all_p = [p for p in projects if p.get("role") != "estimate" and _pos(p.get("records"))]
    ids = est["refs"] if js.truthy(est.get("refs")) else [p["id"] for p in all_p]   # [] is truthy in JS: no references
    refs = [refs_by_id[i] for i in ids if refs_by_id.get(i)]
    eq_res = est_equipment(rows, est, rates, refs)
    Q = est_quantities(eq_res, refs, rates, bundle)
    qover = est.get("qover") or {}
    works = []
    for w in js.values(Q["W"]):
        rt = next((r for r in rates["items"] if norm_name(r["work"]) == norm_name(w["work"])), None)
        q = qover.get(norm_name(w["work"]))
        if q is None:
            q = w["eq"] + w["pkg"] + w["common"]
        o = {**w, "q": q, "qOver": qover.get(norm_name(w["work"])) is not None, "rate": rt["rate"] if rt else None, "rateUnit": rt["unit"] if rt else "",
             "amount": q * rt["rate"] if rt else None}
        um = _and(rt, rt and rt.get("unit"), w["unit"], rt and norm_name(rt.get("unit")) != norm_name(w["unit"]))
        if um is not None:
            o["unitMismatch"] = um
        works.append(o)
    for r in rates["items"]:
        if not any(norm_name(w["work"]) == norm_name(r["work"]) for w in works) and qover.get(norm_name(r["work"])) is not None:
            q = qover[norm_name(r["work"])]
            works.append({"work": r["work"], "unit": r["unit"], "eq": 0, "pkg": 0, "common": 0, "lines": [], "q": q, "qOver": True, "rate": r["rate"], "rateUnit": r["unit"], "amount": q * r["rate"]})
    units = js.unique(d["unit"] for d in refs if js.truthy(d["unit"]))
    return {"refs": refs, "all": all_p, "eqRes": eq_res, "Q": Q, "works": works, "units": units,
            "eqTotal": js.add((e["val"] if js.truthy(e["val"]) else 0) for e in eq_res),
            "wkTotal": js.add((w["amount"] if js.truthy(w["amount"]) else 0) for w in works)}
