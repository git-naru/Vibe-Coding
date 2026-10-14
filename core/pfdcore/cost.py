"""Equipment cost: the manually kept equipment list (with costs) matched to the PFD Equipment List (app.html section 11).

Matching order: tag (ranges and zero padding normalised) → Claude suggestion → similar name; then the viewer's
own picks and typed costs override. The cost state `C` has the record's shape:
{"unit", "list": {file, sheet, headerRow, cols, items}, "pick": {item: key|""}, "ai": {item: [keys]}, "edits": {key: cost}}.
"""
from . import js
from .equipment import stream_tags

TAG_RE = r"(?:\b([A-Z]{1,3})-)?(\d{4})-([A-Z]{2,4})-(\d{1,4})([A-Z]?)((?:\s*[\/~,&]\s*(?:\d{1,4}[A-Z]?|[A-Z])\b)*)"
HOW = {"tag": "Tag 일치", "name": "이름 유사 (확인)", "ai": "Claude 제안 (확인)", "pick": "수동 매칭", "edit": "직접 입력"}


def pad3(n):
    return js.num_str(js.number(n)).rjust(3, "0")


def _s(v):
    """String(v || '')"""
    return js.jstr(v) if js.truthy(v) else ""


def norm_tag(t):
    """3200-pu-1a → 3200-PU-001A (service prefix dropped)"""
    m = js.match(r"^(?:[A-Z]{1,3}-)?(\d{4})-([A-Z]{2,4})-(\d{1,4})([A-Z]?)$", js.sub(r"\s+", "", _s(t).upper()))
    return f"{m.group(1)}-{m.group(2)}-{pad3(m.group(3))}{m.group(4)}" if m else js.trim(_s(t).upper())


def expand_tags(text):
    """"3200-PU-001/002", "001~003", "001A/B", lists separated by , ; or new lines"""
    out = []
    for m in js.finditer(TAG_RE, _s(text).upper()):
        area, code, num, suf, tail = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)

        def base(n):
            return f"{area}-{code}-{pad3(n)}"
        last = js.number(num)
        out.append(base(num) + suf)
        for t in js.finditer(r"([\/~,&])\s*(\d{1,4})?([A-Z]?)", tail or ""):
            op, n, s = t.group(1), t.group(2), t.group(3)
            if n and op == "~":
                k = last + 1
                while k <= js.number(n) and k - last < 50:
                    out.append(base(k) + s)
                    k += 1
                last = js.number(n)
            elif n:
                out.append(base(n) + s)
                last = js.number(n)
            elif s:
                out.append(base(last) + s)
    return js.unique(out)


def eq_key(r):
    return "U:" + r["name"] + "@" + r["sheetKey"] if r.get("untagged") else norm_tag(r["tag"])


def cost_num(v):
    if js.is_num(v):
        return v if js.finite(v) else None
    s = js.sub(r"[^\d.\-]", "", _s(v))
    if not s or s in ("-", "."):
        return None
    x = js.number(s)
    return x if js.finite(x) else None


# ---- reading the list --------------------------------------------------------------------------
COL_RX = {"tag": (r"\btag\b|item\s*no|equip(ment)?\s*(no|number|tag)|기기\s*번호|설비\s*번호|태그", "i"),
          "name": (r"desc|equipment\s*name|^name$|\bname\b|service|설비\s*명|품명|명칭|기기\s*명", "i"),
          "qty": (r"q'?ty|quantity|수량", "i"), "unit": (r"unit\s*(price|cost|rate)|단가", "i"),
          "amount": (r"amount|total|cost|price|금액|설비비|가격|합계|견적", "i")}


def _t(k, c):
    return js.test(COL_RX[k][0], c, COL_RX[k][1])


def _cell(x, j):
    return x[j] if j is not None and 0 <= j < len(x) else None


def parse_cost_workbook(wb):
    """The equipment-cost table in a workbook: the sheet whose header row names tag/name and amount/unit price."""
    best = None
    for sn in wb.sheet_names:
        A = wb.aoa(sn, raw=True)
        for h in range(min(40, len(A))):
            row = [js.trim(js.jstr(c)) for c in A[h]]
            cols = {}
            for j, c in enumerate(row):
                if not c:
                    continue
                if cols.get("tag") is None and _t("tag", c):
                    cols["tag"] = j
                elif cols.get("unit") is None and _t("unit", c):
                    cols["unit"] = j
                elif cols.get("qty") is None and _t("qty", c):
                    cols["qty"] = j
                elif cols.get("name") is None and _t("name", c):
                    cols["name"] = j
                elif _t("amount", c) and not _t("unit", c):
                    cols["amount"] = j   # the last amount-like column is usually the total
            if (cols.get("tag") is None and cols.get("name") is None) or (cols.get("amount") is None and cols.get("unit") is None):
                continue
            items = []
            for r in range(h + 1, len(A)):
                x = A[r]
                tag_raw = js.trim(js.jstr(_cell(x, cols.get("tag")))) if cols.get("tag") is not None else ""
                name = js.trim(js.jstr(_cell(x, cols.get("name")))) if cols.get("name") is not None else ""
                if not tag_raw and not name:
                    continue
                if js.test(r"^(sub-?\s*total|total|합계|소계|계)$", name or tag_raw, "i") or js.test(r"합\s*계|소\s*계|sub-?total|grand\s*total", name, "i"):
                    continue
                qty = cost_num(_cell(x, cols["qty"])) if cols.get("qty") is not None else None
                up = cost_num(_cell(x, cols["unit"])) if cols.get("unit") is not None else None
                am = cost_num(_cell(x, cols["amount"])) if cols.get("amount") is not None else None
                cost = am if am is not None else up * (qty if js.truthy(qty) else 1) if up is not None else None
                tags = expand_tags(tag_raw)
                if cost is None and not tags:
                    continue
                items.append({"i": len(items), "row": r + 1, "tagRaw": tag_raw, "tags": tags, "name": name, "qty": qty, "cost": cost})
            head = row[cols["amount"]] if cols.get("amount") is not None else row[cols["unit"]]
            m1 = js.match(r"\(([^)]+)\)", head)
            m2 = js.match(r"USD|KRW|EUR|JPY|CNY|백만원|천원|억원|원|\$", head, "i")
            unit = js.trim((m1.group(1) if m1 else None) or (m2.group(0) if m2 else None) or "")
            score = sum(2 for it in items if it["cost"] is not None) + sum(1 for it in items if it["tags"])
            if items and (not best or score > best["score"]):
                best = {"sheet": sn, "headerRow": h + 1, "cols": {k: row[j] for k, j in cols.items()}, "unit": unit, "items": items, "score": score}
            break   # first header-looking row of a sheet decides it
    if not best:
        return None
    del best["score"]
    return best


def load_cost_list(C, lst, file):
    """A newly read list replaces the old one (and its picks and Claude pairs); typed costs and the unit stay."""
    C = C or {"edits": {}, "pick": {}, "ai": {}}
    return {**C, "list": {**lst, "file": file}, "unit": C.get("unit") or lst.get("unit") or "", "pick": {}, "ai": {}}


# ---- matching ----------------------------------------------------------------------------------
def name_tokens(s):
    return dict.fromkeys(js.match_all(r"[A-Z]{3,}|[가-힣]{2,}", js.sub(r"\(.*?\)", " ", _s(s).upper())))


def jacc(a, b):
    if not a or not b:
        return 0
    n = sum(1 for x in a if x in b)
    return n / (len(a) + len(b) - n)


def compute_costs(C, rows):
    """Equipment costs by equipment key: {byKey, assign, how, unmatched, total, outside, pfd, keyOf}."""
    if not C:
        return None
    pick, ai_pairs, edits = C.get("pick") or {}, C.get("ai") or {}, C.get("edits") or {}
    key_of = [eq_key(r) for r in rows]
    key_set = set(key_of)
    idx, base_idx = {}, {}
    for j, k in enumerate(key_of):
        if rows[j].get("untagged"):
            continue
        idx.setdefault(k, []).append(k)
        base_idx.setdefault(js.sub("[A-Z]$", "", k, count=1), []).append(k)
    items = ((C.get("list") or {}).get("items")) or []
    assign, how, tagged = {}, {}, set()
    for it in items:   # 1. tags
        i = js.jstr(it["i"])
        if i in pick:
            continue
        ks = js.unique(k for t in it["tags"] for k in (idx.get(t) or base_idx.get(t) or idx.get(js.sub("[A-Z]$", "", t, count=1)) or []))
        if ks:
            assign[i] = ks
            how[i] = "tag"
            tagged.update(ks)
    free = [[k, j, name_tokens(rows[j]["name"])] for j, k in enumerate(key_of) if k not in tagged]
    for it in items:   # 2. Claude suggestion, 3. similar name (unique best)
        i = js.jstr(it["i"])
        if i in pick or js.truthy(assign.get(i)):
            continue
        ai = [k for k in (ai_pairs.get(i) or []) if k in key_set]
        if ai:
            assign[i] = ai
            how[i] = "ai"
            continue
        if it["tags"]:
            continue   # a tag that is not on the PFD is not guessed by name
        t = name_tokens(it["name"])
        sc = js.sort([[k, jacc(t, tk)] for k, _, tk in free], lambda a, b: b[1] - a[1])
        if sc and sc[0][1] >= 0.6 and (len(sc) < 2 or sc[0][1] - sc[1][1] >= 0.15):
            assign[i] = [sc[0][0]]
            how[i] = "name"
    for i, k in js.entries(pick):
        if js.truthy(k) and k in key_set:
            assign[i] = [k]
            how[i] = "pick"
        elif k == "":
            assign[i] = []
            how[i] = "none"
    by_key = {}
    for it in items:
        i = js.jstr(it["i"])
        ks = assign.get(i) or []
        if not ks or it["cost"] is None:
            continue
        for k in ks:
            b = by_key.get(k)
            if b is None:
                b = by_key[k] = {"cost": 0, "how": how.get(i), "items": []}
            b["cost"] += it["cost"] / len(ks)
            b["items"].append(it["i"])
            if len(ks) > 1:
                b["split"] = len(ks)
    for k, v in js.entries(edits):
        if k in key_set:
            by_key[k] = {"cost": v, "how": "edit", "items": (by_key.get(k) or {}).get("items") or []}
    unmatched = [it for it in items if not (assign.get(js.jstr(it["i"])) or [])]
    total = js.add((it["cost"] if js.truthy(it["cost"]) else 0) for it in items)
    outside = js.add((it["cost"] if js.truthy(it["cost"]) else 0) for it in unmatched)
    pfd = js.add(b["cost"] for b in js.values(by_key))
    return {"byKey": by_key, "assign": assign, "how": how, "unmatched": unmatched, "total": total, "outside": outside, "pfd": pfd, "keyOf": key_of}


def cost_of_nodes(K, nodes):
    """Costs of the boxes in a flow card: tags in the box id or subtitle (hand-made boxes)."""
    if not K:
        return None
    tags = {norm_tag(t) for n in nodes for t in [*stream_tags(n.get("id")), *stream_tags(n.get("sub") or n.get("tags") or "")]}
    s, n, of = 0, 0, 0
    for k in K["keyOf"]:
        if k not in tags and js.sub("[A-Z]$", "", k, count=1) not in tags:
            continue
        of += 1
        b = K["byKey"].get(k)
        if b:
            s += b["cost"]
            n += 1
    return {"sum": s, "n": n, "of": of} if of else None


# ---- Claude pairs what tags and names could not ------------------------------------------------
def cost_prompt(un, cands):
    return f"""[[COST-MATCH]]
너는 EPC 견적 엔지니어다. 왼쪽은 사람이 관리하는 설비비 목록 중 PFD Equipment List와 Tag로 맞지 않은 항목, 오른쪽은 아직 설비비가 없는 PFD 설비다.
같은 설비(또는 설비 묶음)를 가리키는 짝을 찾는다.

규칙
- 설비명·종류·Tag 번호 체계(오기, 자릿수, 접두어 차이)를 보고 판단한다. 확실하지 않으면 짝을 만들지 않는다.
- 목록 항목 하나가 PFD 설비 여러 개(예: 펌프 1/2, 같은 탱크 여러 기)를 가리키면 keys에 모두 넣는다.
- PFD에 없는 항목(예: 예비품, 운송, 설치, 공통 자재)은 넣지 않는다.

출력은 JSON 하나만: {{"pairs":[{{"item":3,"keys":["3200-PU-001","3200-PU-002"],"why":"짧은 근거"}}]}}

## 설비비 목록 (item | Tag 원문 | 설비명 | 수량)
{chr(10).join(f"{js.jstr(it['i'])} | {it['tagRaw'] or '-'} | {it['name'] or '-'} | {'-' if it['qty'] is None else js.jstr(it['qty'])}" for it in un)}

## PFD 설비 (key | Tag | 이름 | 종류 | Area)
{chr(10).join(f"{eq_key(r)} | {r['tag']} | {r['name']} | {r['kind']} | {r['area']}" for r in cands)}"""


def cost_ai_request(K, rows):
    """What the app sends Claude: up to 200 unmatched list rows and 600 PFD rows still without a cost."""
    un = K["unmatched"][:200]
    cands = [r for r in rows if not K["byKey"].get(eq_key(r))][:600]
    return un, cands


def apply_cost_ai(C, un, cands, answer):
    """Keep Claude's pairs whose item and keys exist; returns the number of list rows paired."""
    ok = {eq_key(r) for r in cands}
    n = 0
    pairs = answer.get("pairs") if isinstance(answer, dict) and isinstance(answer.get("pairs"), list) else []
    C.setdefault("ai", {})
    for p in pairs:
        p = p if isinstance(p, dict) else {}
        ks = [js.jstr(k) for k in (p.get("keys") if isinstance(p.get("keys"), list) else [])]
        ks = [k for k in ks if k in ok]
        item = js.number(p.get("item"))
        if ks and any(js.number(it["i"]) == item for it in un):
            C["ai"][js.num_str(item)] = ks
            n += 1
    return n
