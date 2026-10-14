"""Equipment List from the PFD text layer, and stream values from a flow result (app.html section 10).

`extract_equipment(sheet)` finds the labels on one sheet; `build_equipment(sheets)` makes the whole list
(rows, tags cited but not drawn, area names); `link_equipment_to_flow(rows, tabs)` adds stream values.
"""
from . import js
from .sheets import DWG_1, DWG_SRC, is_badge, norm_dwg
from .streams import num_parse

EQ_TAG = r"(?:\b[A-Z]{1,3}-)?\d{4}-[A-Z]{2,4}-\d{2,3}[A-Z]?\b"            # optional service prefix: WF-6400-FH-003
EQ_TAGLINE = r"^\s*(?:(?:[A-Z]{1,3}-)?\d{4}-[A-Z]{2,4}-\d{2,3}[A-Z]?\s*)+$"
EQ_PAREN = r"^\([A-Z][A-Z .\-/]*\)$"
EQ_STOP = r"^(NOTE\b|SEE\b|FROM\b|TO\b|\(|:|NOM\.|SPILLS$|BY VENDOR$|\d+[a-z]?(,[a-z])*$)"
EQ_REMARK = r"^(STAND-?BY|SPARE|FUTURE)$"
EQ_REF = r"(\d{4})-([A-Z]{2,4})-(\d{3,4}[A-Z]?)((?:\s*[/@]\s*\d{3,4}[A-Z]?(?![\d-]))*)"
EQ_NOUN = {"AG": "AGITATOR", "PU": "PUMP", "TK": "TANK", "FA": "FAN", "CV": "CONVEYOR", "FL": "FILTER", "HX": "EXCHANGER", "RX": "REACTOR"}
EQ_TYPE = {
    "PU": "펌프", "TK": "탱크", "AG": "교반기", "SS": "안전샤워·세안기", "PF": "필터", "RX": "반응조", "GV": "게이트 밸브", "FL": "필터", "FA": "팬·블로어", "BA": "진동기·피더",
    "CV": "컨베이어", "ML": "폰드", "FE": "스크루 피더·컨베이어", "DC": "필터", "HX": "열교환기", "RV": "로터리 밸브", "DR": "건조기", "AR": "공기 저장조", "BN": "빈·호퍼",
    "IH": "전기 히터", "SR": "스크러버", "MX": "믹서", "CP": "압축기", "MT": "자석 분리기", "DP": "폰드", "RF": "릴리프·진공 밸브", "VT": "벤투리", "BL": "팬·블로어",
    "SP": "스탠드파이프", "PK": "패키지 설비", "IX": "이온교환탑", "ST": "스택", "BU": "버너", "HT": "호이스트", "MU": "마대 하역기", "SO": "빈·호퍼", "TH": "시크너·청징조",
    "RK": "레이크", "SK": "야적장", "MA": "자석 분리기", "DI": "디젤 디스펜서", "WS": "연수기", "BO": "보일러", "SC": "계량기", "SL": "슬레이커", "VS": "진동 스크린", "PL": "폰드",
    "FX": "필터", "CS": "응축수 분리기", "CY": "사이클론", "CC": "연소실", "BX": "배출 박스", "HE": "칠러", "RC": "냉각기", "MV": "밸브", "PM": "팔레트 매거진", "FM": "충전기",
    "TR": "공압 이송 용기", "FP": "패키지 설비", "SI": "사일렌서", "FW": "피드웰"}
EQ_BYNAME_FIRST = [["HYDRANT", "소화전·모니터"], ["HOSE REEL", "호스릴"]]          # the name decides before the code (FM is also a filling machine)
EQ_BYNAME = [["TANK", "탱크"], ["SEPARATOR", "분리기"], ["POND", "폰드"], ["MACHINE", "포장기"], ["PUMP", "펌프"], ["FILTER", "필터"], ["SYSTEM", "패키지 설비"],
             ["SPRINKLER", "소화 설비"], ["BASKET", "스트레이너"], ["CONTAINER", "컨테이너"], ["SKIP", "컨테이너"], ["WASHING STATION", "안전샤워·세안기"], ["DRUM", "드럼"],
             ["IBC", "탱크"], ["VESSEL", "용기"], ["SCALE", "계량기"], ["VENT", "벤트 스택"], ["MOTOR", "구동 장치"], ["DRIVE", "구동 장치"], ["HOPPER", "빈·호퍼"], ["BIN", "빈·호퍼"],
             ["MIXER", "믹서"], ["FAN", "팬·블로어"], ["BLOWER", "팬·블로어"], ["CONVEYOR", "컨베이어"], ["FEEDER", "스크루 피더·컨베이어"], ["EXCHANGER", "열교환기"], ["COOLER", "냉각기"], ["HEATER", "히터"]]
EQ_MOVERS = {"PU", "FA", "BL", "CP", "BO"}                               # rated by what they deliver: outlet stream
EQ_UNTAGGED_KW = r"\b(PUMPS?|TANKS?|FILTERS?|STRAINER|TRAP|VENT|SEPARATOR|COOLER|HEATER|MIXER|SCREEN|CONVEYOR|FEEDER|BIN|HOPPER|SILO|PONDS?|REACTOR|COLUMN|DRYER|FAN|BLOWER|COMPRESSOR|VESSEL|PACKAGE|SKID|SCALE|CYCLONE|AGITATOR|EXCHANGER|BOILER|THICKENER|CLARIFIER|SCRUBBER|SYSTEM|CHILLER|EJECTOR|EDUCTOR|CONTAINER|STATION|DRUM)\b"
EQ_NOT_EQUIP = r"\b(TRUCKS?|WAREHOUSE|PARAPET|PIT|TRENCH|CHANNEL|DISTRIBUTION|LOADER|FORKLIFT)\b"
SENTENCE_WORDS = r"\b(THE|IS|ARE|BE|WILL|MUST|FOR|AND|OF|TO|IN|ON|WITH|ONLY|THIS|THAT|NOT)\b"


def cx_of(it):
    return (it["x0"] + it["x1"]) / 2


def x_overlap(a, b, pad=0.004):
    return a["x0"] < b["x1"] + pad and a["x1"] > b["x0"] - pad


def sheet_grid(items):
    cols, rws = [], []
    for it in items:
        t = js.trim(it["s"])
        if it["y0"] < 0.03 and js.test(r"^\d{1,2}$", t):
            cols.append([cx_of(it), t])
        elif it["x0"] < 0.02 and js.test("^[A-H]$", t):
            rws.append([(it["y0"] + it["y1"]) / 2, t])
    return {"cols": cols, "rws": rws}


def zone_of(grid, x, y):
    if not grid or not grid["cols"] or not grid["rws"]:
        return ""

    def near(arr, v):
        b = arr[0]
        for a in arr[1:]:
            if abs(a[0] - v) < abs(b[0] - v):
                b = a
        return b
    return near(grid["rws"], y)[1] + "-" + near(grid["cols"], x)[1]


def sheet_area(sh):
    items = sh["items"]
    a = next((it for it in items if js.test("PROCESS FLOW DIAGRAM", it["s"])), None)
    code = name = ""
    if a:
        prev = js.sort([b for b in items if b["y1"] <= a["y0"] + 0.002 and a["y0"] - b["y0"] < 0.03 and abs(cx_of(b) - cx_of(a)) < 0.08],
                       lambda p, q: q["y0"] - p["y0"])
        m = js.match(r"^(\d{4})\s*-\s*(.+)$", prev[0]["s"]) if prev else None
        if m:
            code, name = m.group(1), js.trim(m.group(2))
    if not code and sh.get("dwg"):
        m = js.match(r"-(\d{4})-[A-Z]{2}-", sh["dwg"])
        if m:
            code = m.group(1)
    return {"code": code, "name": name}


def extract_equipment(sh):
    """One sheet: equipment labels = name lines above a tag that stands alone on its line, remarks under it."""
    L = [it for it in sh["items"] if it["y0"] < 0.97]
    tagl = [it for it in L if js.test(EQ_TAGLINE, it["s"])]
    used, groups = set(), []
    suffix = {}      # a type noun written just UNDER a tag ('4100-AG-002' / 'AGITATOR') ends that label
    for t in tagl:
        m = js.match(r"\d{4}-([A-Z]+)-", t["s"])
        noun = m and EQ_NOUN.get(m.group(1))
        s = noun and next((x for x in L if js.trim(x["s"]) == noun and 0 < x["y0"] - t["y0"] < 0.0115 and abs(cx_of(x) - cx_of(t)) < 0.006), None)
        if s:
            suffix[id(t)] = s
    suffix_lines = {id(x) for x in suffix.values()}
    for l in js.sort(tagl, lambda p, q: p["y0"] - q["y0"]):
        if id(l) in used:
            continue
        grp = [l]
        used.add(id(l))
        while True:   # stacked tags under one name
            last = grp[-1]
            nx = next((m for m in tagl if id(m) not in used and abs(m["x0"] - last["x0"]) < 0.006 and 0 < m["y0"] - last["y0"] < 0.015), None)
            if not nx:
                break
            grp.append(nx)
            used.add(id(nx))
        c = cx_of(grp[0])
        name, rem, top = [], [], grp[0]
        for k in range(5):
            lim = 0.019 if k == 0 else 0.0125
            up = [m for m in L if m is not top and id(m) not in suffix_lines and 0 < top["y0"] - m["y0"] < lim and x_overlap(m, top)
                  and top["y0"] - m["y0"] >= 0.85 * (m["y1"] - m["y0"]) and abs(cx_of(m) - c) < 0.009
                  and not js.test(EQ_TAGLINE, m["s"]) and (js.test(EQ_PAREN, js.trim(m["s"])) or not js.test(EQ_STOP, js.trim(m["s"])))
                  and not js.test(DWG_SRC, m["s"])]
            if not up:
                break
            m = js.reduce_max(up, lambda b, a: b["y0"] > a["y0"])
            top = m
            t = js.trim(m["s"])
            if js.test(EQ_PAREN, t):
                if name:
                    break
                rem.append(t)
                continue
            # a lone leading digit is usually a revision triangle; drop it when the rest centres better over the tag
            w = js.split(r"\s+", t)
            if len(w) > 1 and js.test(r"^\d$", w[0]):
                per = (m["x1"] - m["x0"]) / js.length(t)
                rest0 = m["x0"] + per * (js.length(w[0]) + 1)
                if abs((rest0 + m["x1"]) / 2 - c) < abs(cx_of(m) - c):
                    w = w[1:]
            name.insert(0, " ".join(w))
        bot = grp[-1]
        for k in range(3):
            dn = [m for m in L if m is not bot and 0 < m["y0"] - bot["y0"] < 0.0125 and x_overlap(m, bot)
                  and (js.test(EQ_PAREN, js.trim(m["s"])) or js.test(r"^NOM\. ?VOL", js.trim(m["s"])) or js.test(EQ_REMARK, js.trim(m["s"])))]
            if not dn:
                break
            m = js.reduce_max(dn, lambda b, a: b["y0"] < a["y0"])
            rem.append(js.trim(m["s"]))
            bot = m
        tags, boxes, side = [], {}, {}
        for g in grp:
            for t in js.match_all(EQ_TAG, g["s"]):
                tags.append(t)
                boxes[t] = [g["x0"], g["y0"], g["x1"], g["y1"]]
                # (SPARE)/(STAND-BY) written beside a tag instead of under the group
                sd = next((m for m in L if abs(m["y0"] - g["y0"]) < 0.004 and 0 < m["x0"] - g["x1"] < 0.013 and js.test(EQ_PAREN, js.trim(m["s"]))), None)
                if sd:
                    side[t] = js.trim(sd["s"])
        sfx = suffix.get(id(grp[-1]))
        if sfx and not (name and name[-1].endswith(js.trim(sfx["s"]))):
            name.append(js.trim(sfx["s"]))
        groups.append({"tags": tags, "name": " ".join(name), "remarks": rem, "side": side, "boxes": boxes})
    # tags cited elsewhere (FROM/TO connectors, notes) — to list what is referenced but never drawn
    refs = {}
    for l in L:
        if js.test(EQ_TAGLINE, l["s"]):
            continue
        for m in js.finditer(EQ_REF, l["s"]):
            nums = [m.group(3), *[x.group(1) for x in js.finditer(r"[/@]\s*(\d{3,4}[A-Z]?)", m.group(4))]]
            if "@" in m.group(4) and len(nums) == 2 and js.test(r"^\d+$", nums[0]) and js.test(r"^\d+$", nums[1]):
                a, b = int(nums[0]), int(nums[1])
                nums = []
                i = a
                while i <= b and len(nums) < 50:
                    nums.append(str(i))
                    i += 1
            for n in nums:   # drawings pad a zero too many at times (0010)
                d = js.match(r"^(\d+)([A-Z]?)$", n)
                refs[f"{m.group(1)}-{m.group(2)}-{js.num_str(js.number(d.group(1))).rjust(3, '0')}{d.group(2)}"] = True
    # equipment drawn with a name but no tag (candidates, 미확인)
    untagged, tb = [], sh.get("imgs") or []
    for l in L:
        t = js.trim(l["s"])
        if not js.test(EQ_UNTAGGED_KW, t) or js.test(EQ_NOT_EQUIP, t) or js.test(EQ_TAG, t):
            continue
        if (js.test("^[(:]", t) or js.test(r"^\d+\.\s", t) or js.length(t) > 45 or js.test(r"\.$", t) or js.test(r"^(FROM|TO)\b", t)
                or l["y0"] > 0.83 or (l["x0"] > 0.6 and l["y0"] > 0.8)):
            continue
        if len(js.match_all(SENTENCE_WORDS, t)) >= 2:   # a sentence (notes), not a label
            continue
        if any(l["x0"] > b[0] and l["x1"] < b[2] and l["y0"] > b[1] and l["y1"] < b[3] for b in tb):
            continue
        if any(0 < tl["y0"] - l["y0"] < 0.045 and abs(cx_of(tl) - cx_of(l)) < 0.03 for tl in tagl):   # part of a tagged label
            continue
        if any(js.test(DWG_1, norm_dwg(m["s"])) and abs(m["y0"] - l["y0"]) < 0.03 and x_overlap(m, l, 0) for m in L):   # off-page connector block
            continue
        if any(m is not l and abs(m["y0"] - l["y0"]) < 0.003 and m["x1"] < l["x0"] and l["x0"] - m["x1"] < 0.01 and js.test(r"^\d+\.$", js.trim(m["s"])) for m in L):   # numbered note
            continue
        lines, topl = [t], l
        for k in range(2):
            up = next((m for m in L if m is not topl and 0 < topl["y0"] - m["y0"] < 0.0125 and abs(cx_of(m) - cx_of(l)) < 0.01 and not js.test(EQ_TAGLINE, m["s"])
                       and not js.test(EQ_STOP, js.trim(m["s"])) and not js.test(DWG_1, norm_dwg(m["s"])) and not is_badge(m["s"])), None)
            if not up:
                break
            lines.insert(0, js.trim(up["s"]))
            topl = up
        botl = l
        for k in range(2):   # label continues below ('WASHING STATION OF' / 'POLYVALENT SOLUTION' / '(DIPHOTERINE)')
            dn = next((m for m in L if m is not botl and 0 < m["y0"] - botl["y0"] < 0.0125 and abs(cx_of(m) - cx_of(l)) < 0.012 and not js.test(EQ_TAGLINE, m["s"])
                       and not js.test(r"^(NOTE\b|FROM\b|TO\b|:)", js.trim(m["s"])) and not js.test(DWG_1, norm_dwg(m["s"])) and not is_badge(m["s"])), None)
            if not dn:
                break
            lines.append(js.trim(dn["s"]))
            botl = dn
        if any(u["box"][0] <= l["x1"] and u["box"][2] >= l["x0"] and u["box"][1] <= l["y1"] + 0.001 and u["box"][3] >= l["y0"] - 0.001 for u in untagged):
            continue   # already inside another candidate's label
        untagged.append({"name": " ".join(lines), "box": [min(topl["x0"], l["x0"], botl["x0"]), topl["y0"], max(topl["x1"], l["x1"], botl["x1"]), botl["y1"]]})
    return {"groups": groups, "refs": list(refs), "untagged": untagged}


def expand_names(name, tags):
    """'FEED PUMPS 1/2' over two tags → ['FEED PUMP 1', 'FEED PUMP 2'] (also A/B, 1,2,3 and 2@8)."""
    suffix = ""
    m = js.match(r"(\d+)\s*@\s*(\d+)\s*$", name)
    if m:
        nums = [str(i) for i in range(int(m.group(1)), int(m.group(2)) + 1)]
    else:
        m = js.match(r"(?<![\w-])((?:\d+|[A-Z])(?:\s*(?:\/|,|&|AND)\s*(?:\d+|[A-Z]))+)\s*(\([^)]*\))?\s*$", name)
        if not m:
            return [[name for _ in tags], "mismatch" if js.test(r"\d+\s*$", name) else "plain"]
        nums = js.split(r"\s*(?:\/|,|&|AND)\s*", m.group(1))
        suffix = " " + m.group(2) if m.group(2) else ""
    if len(nums) != len(tags):
        return [[name for _ in tags], "mismatch"]
    base = js.sub("PONDS$", "POND", js.sub("PUMPS$", "PUMP", js.trim_end(name[: m.start()]), count=1), count=1)
    return [[f"{base} {n}{suffix}" for n in nums], "ok"]


def eq_kind(code, name):
    N = name.upper()
    f = next((x for x in EQ_BYNAME_FIRST if x[0] in N), None)
    if f:
        return f[1]
    if code and EQ_TYPE.get(code) and code not in ("DA", "WP"):
        return EQ_TYPE[code]
    b = next((x for x in EQ_BYNAME if x[0] in N), None)
    return b[1] if b else (code or "")


_CONF = {"high": "높음", "medium": "보통"}


def build_equipment(sheets):
    """Whole list from every sheet read: {rows, refsMissing, areaNames}. Sheets need `eq`, `area`, `grid`."""
    rows, drawn, cited, area_names = [], {}, {}, {}
    for sh in sheets:
        if not sh.get("eq"):
            continue
        if sh["area"]["code"] and sh["area"]["name"]:
            area_names[sh["area"]["code"]] = area_names.get(sh["area"]["code"]) or sh["area"]["name"]
    for sh in sheets:
        if not sh.get("eq"):
            continue
        for g in sh["eq"]["groups"]:
            names, how = expand_names(g["name"], g["tags"]) if len(g["tags"]) > 1 else [[g["name"]], "ok"]
            spare_last = js.test("SPARE|STAND", " ".join([*g["remarks"], *g["side"].values()]), "i")
            flags, group_note = [], ""
            if how == "plain":
                group_note = f"같은 이름 {len(g['tags'])}기"
            elif how == "mismatch" and len(g["tags"]) == 2 and spare_last:
                group_note = "같은 호기 운전 1기 + 예비 1기"
            elif how == "mismatch":
                flags.append(f"이름 하나에 Tag {len(g['tags'])}개인데 호기 번호가 맞지 않음")
            if not g["name"]:
                flags.append("이름 미판독")
            if len(js.split(r"\s+", g["name"])) > 7:
                flags.append("이름이 길다 — 주변 글자 섞임 확인")
            vol = next((r for r in g["remarks"] if r.startswith("NOM")), None)
            other = [js.sub(r"^\(|\)$", "", r) for r in g["remarks"] if not r.startswith("NOM")]
            for i, tag in enumerate(g["tags"]):
                mt = js.match(r"(\d{4})-([A-Z]+)-", tag)
                area, code = mt.group(1), mt.group(2)
                status, notes = "운전", ([group_note] if group_note else [])
                for o in other:
                    u = js.sub(r"\s", "", o.upper())
                    if js.test("^(STAND-?BY|SB)$", u):
                        if i == len(g["tags"]) - 1:
                            status = "예비(Stand-by)"
                    elif u == "SPARE":
                        if i == len(g["tags"]) - 1:
                            status = "예비(Spare)"
                    elif u == "FUTURE":
                        status = "향후(Future)"
                    else:
                        notes.append(o)
                if g["side"].get(tag):
                    status = "예비(Spare)" if js.test("SPARE", g["side"][tag], "i") else "예비(Stand-by)"
                f = list(flags)
                if sh["area"]["code"] and area != sh["area"]["code"]:
                    f.append(f"{sh['area']['code']} 시트에 그려진 {area} 설비")
                b = g["boxes"][tag]
                mv = js.match(r"([\d.]+)\s*m3", vol) if vol else None
                rows.append({"tag": tag, "area": area, "name": names[i], "kind": eq_kind(code, names[i]), "status": status, "note": ", ".join(notes),
                             "vol": (js.number(mv.group(1)) if mv else js.trim(vol.split(":")[-1])) if vol else "",
                             "dwg": sh.get("dwg") or "", "page": sh["page"], "file": sh["file"], "sheetKey": sh["key"],
                             "zone": zone_of(sh.get("grid"), cx_of({"x0": b[0], "x1": b[2]}), (b[1] + b[3]) / 2), "box": b, "flags": f})
                drawn[js.sub(r"^[A-Z]{1,3}-(?=\d{4})", "", tag, count=1)] = True
        for u in sh["eq"]["untagged"]:
            rows.append({"tag": "(Tag 없음)", "area": sh["area"]["code"], "name": u["name"], "kind": eq_kind("", u["name"]), "status": "미확인", "note": "", "vol": "",
                         "dwg": sh.get("dwg") or "", "page": sh["page"], "file": sh["file"], "sheetKey": sh["key"],
                         "zone": zone_of(sh.get("grid"), (u["box"][0] + u["box"][2]) / 2, (u["box"][1] + u["box"][3]) / 2), "box": u["box"], "untagged": True,
                         "flags": ["도면에 Tag 없이 이름만 있는 설비 후보 — 도면에서 확인 후 목록 포함 여부 결정"]})
        for v in sh.get("eqVision") or []:
            rows.append({"tag": "(Tag 없음)", "area": sh["area"]["code"], "name": "(그림) " + v["ko"], "kind": eq_kind("", v["what"].upper() + " " + v["ko"]), "status": "미확인",
                         "note": " · ".join(x for x in [v["what"], "가까운 설비 " + v["near"] if v["near"] else ""] if x), "vol": "",
                         "dwg": sh.get("dwg") or "", "page": sh["page"], "file": sh["file"], "sheetKey": sh["key"],
                         "zone": zone_of(sh.get("grid"), v["pt"][0], v["pt"][1]), "box": v["box"], "untagged": True, "vision": True,
                         "flags": [f"글자 없이 그림으로만 그려진 설비 후보(Claude 그림 판독, 신뢰 {_CONF.get(v['conf'], '낮음')}) — 도면에서 확인"]})
        for r in sh["eq"]["refs"]:
            cited.setdefault(r, {})[sh["key"]] = True
    rows = js.sort(rows, lambda a, b: js.locale_compare(a["area"], b["area"]) or ((1 if a.get("untagged") else 0) - (1 if b.get("untagged") else 0))
                   or js.locale_compare(a["tag"], b["tag"]) or (a["page"] - b["page"]))
    input_areas = {s["area"]["code"] for s in sheets if s.get("eq")}
    refs_missing = []
    for t in sorted(k for k in cited if k not in drawn and not js.test("-0{3}$", k)):
        a, _, n = t.split("-")[:3]
        twin = [x for x in drawn if x.startswith(a + "-") and x.endswith("-" + n) and x != t]
        why = (f"{a} Area 도면이 입력에 없음 — 그 도면의 설비를 가리키는 정상 참조" if a not in input_areas
               else f"Tag 오기로 보임 — 같은 번호의 {', '.join(twin)}가 도면에 있음" if twin
               else f"{a} Area 도면은 입력에 있는데 설비로 그려져 있지 않음 (문구·주석에만 언급)")
        refs_missing.append({"tag": t, "sheets": ", ".join(cited[t]), "why": why})
    return {"rows": rows, "refsMissing": refs_missing, "areaNames": area_names}


def stream_tags(text):
    """Equipment tags named in a stream end ('4300-RX-008', '4300-PU-001/002', 'TK-073' after an area)."""
    out, area = [], None
    for m in js.finditer(r"(?:(\d{4})-)?([A-Z]{2,4})-(\d{3})((?:\s*\/\s*\d{3})*)", js.jstr(text if js.truthy(text) else "")):
        area = m.group(1) or area
        if not area:
            continue
        for n in [m.group(3), *js.match_all(r"\d{3}", m.group(4))]:
            out.append(f"{area}-{m.group(2)}-{n}")
    return out


def flow_tabs(bundle=None, result=None):
    """The tabs whose streams feed the list: a bundle's tabs, or one flow result as a tab."""
    if bundle:
        return bundle["tabs"]
    if result:
        return [{"label": (result.get("meta") or {}).get("title") or "흐름도", "flow": result}]
    return []


def link_equipment_to_flow(rows, tabs):
    """Stream data from the flow tabs: a tag named in a stream's ends gets that stream's values (row['mb']).
    Returns the labels of the tabs used (the app's EQ.mbTitle)."""
    for r in rows:
        r.pop("mb", None)
    if not tabs:
        return ""

    def add(m, t, i):
        xs = m.setdefault(t, [])
        if i not in xs:
            xs.append(i)

    def num(v):
        x = num_parse(v, False)
        return x if js.finite(x) else None

    maps = []
    for t in tabs:   # per tab: which streams start (out) and end (in) at each tag; the main stream tab is read first
        D = t.get("flow")
        if not D or not D.get("streams"):
            continue
        inl, outl = {}, {}
        for e in D.get("edges") or D.get("links") or []:
            for x in stream_tags(e.get("from")):
                add(outl, x, e.get("id"))
            for x in stream_tags(e.get("to")):
                add(inl, x, e.get("id"))
        for sid, st in js.entries(D["streams"]):
            if not js.truthy(st.get("v")):
                continue
            for x in stream_tags(st.get("from")):
                add(outl, x, sid)
            for x in stream_tags(st.get("to")):
                add(inl, x, sid)
        maps.append({"label": t.get("label"), "D": D, "inl": inl, "outl": outl})
    used = {}
    for r in rows:
        if r.get("untagged"):
            continue
        key = js.sub(r"^[A-Z]{1,3}-(?=\d{4})", "", r["tag"], count=1)
        mc = js.match(r"\d{4}-([A-Z]+)-", key)
        code = mc.group(1) if mc else None
        for m in maps:
            D = m["D"]

            def has(i):
                s = D["streams"].get(js.jstr(i))
                return bool(s) and js.truthy(s.get("v"))
            ins = [i for i in m["inl"].get(key, []) if has(i)]
            outs = [i for i in m["outl"].get(key, []) if has(i)]
            basis = (outs or ins) if code in EQ_MOVERS else (ins or outs)
            if not basis:
                continue
            vs = [D["streams"][js.jstr(i)]["v"] for i in basis]

            def total(k, alt=None):
                xs = []
                for v in vs:
                    x = num(v.get(k))
                    if x is None:
                        x = num(v.get(alt)) if alt else None
                    if x is not None:
                        xs.append(x)
                return js.js_round(js.add(xs) * 1000) / 1000 if xs else ""

            def span(k):
                xs = sorted(js.unique(x for x in (num(v.get(k)) for v in vs) if x is not None))
                return "" if not xs else xs[0] if len(xs) == 1 else f"{js.num_str(xs[0])}–{js.num_str(xs[-1])}"
            cats = D.get("categories") or {}
            r["mb"] = {"tab": m["label"], "in": ", ".join(map(js.jstr, ins)), "out": ", ".join(map(js.jstr, outs)), "basis": ", ".join(map(js.jstr, basis)),
                       "fluid": ", ".join(x for x in js.unique((cats.get(D["streams"][js.jstr(i)].get("cat")) or {}).get("label") or "" for i in basis) if x),
                       "dm": total("dm"), "nm": total("nm"), "dx": total("dxm", "dsm"), "T": span("T"), "P": span("P"), "rho": span("rho"), "sol": span("sol")}
            if len(basis) > 1:
                r["mb"]["note"] = f"기준 Stream {len(basis)}개 합산"
            used[m["label"]] = True
            break
    return ", ".join(js.jstr(x) for x in used)


def row_flags(r):
    return "; ".join([*r["flags"], *([r["mb"]["note"]] if r.get("mb") and r["mb"].get("note") else [])])


# ---- F37: equipment drawn only as a symbol (Claude reads the sheet images) ---------------------
def vision_prompt(sh, n_img, boxes):
    known = []
    for g in sh["eq"]["groups"]:
        for t in g["tags"]:
            b = g["boxes"][t]
            known.append(f"{t}|{g['name']}|{js.to_fixed(cx_of({'x0': b[0], 'x1': b[2]}), 3)}|{js.to_fixed((b[1] + b[3]) / 2, 3)}")
    for u in sh["eq"]["untagged"]:
        known.append(f"(Tag 없음)|{u['name']}|{js.to_fixed((u['box'][0] + u['box'][2]) / 2, 3)}|{js.to_fixed((u['box'][1] + u['box'][3]) / 2, 3)}")
    tiles = "\n".join(f"이미지 {i + 1}: 페이지 x {js.to_fixed(b[0], 2)}~{js.to_fixed(b[2], 2)}, y {js.to_fixed(b[1], 2)}~{js.to_fixed(b[3], 2)}" for i, b in enumerate(boxes))
    dwg = sh.get("dwg") or sh["key"]
    return f"""[[EQUIP-VISION {dwg}]]
너는 공정 설계 엔지니어다. PFD 한 장(도면 번호 {sh.get('dwg') or '-'}, 제목 {sh.get('title') or '-'})을 나눈 이미지 {n_img}장에서, 아래 "이미 찾은 설비"에 없는 설비 기호를 찾는다. 특히 이름도 Tag도 없이 그림으로만 그려진 설비를 찾는다.
조각이 겹치므로 같은 설비가 두 이미지에 보이면 한 번만 적는다.
{tiles}

설비로 볼 것: 펌프, 탱크·용기·드럼·IBC, 바퀴 달린 컨테이너·스킵·빈·호퍼, 필터, 열교환기, 교반기·모터 구동부, 컨베이어·피더, 팬·블로어, 압축기, 벤트 스택·사일렌서, 스크러버, 믹서, 저울, 세척 설비, 패키지 설비.
빼는 것: 트럭·지게차·로더 같은 차량, 건물·창고, 피트·트렌치·방류벽 같은 토목 구조물, 밸브·계기·배관·헤더, Stream 번호 배지, 시트 연결 화살표와 그 글자, 패키지 경계선, 사람, 범례·표·주석·도면 제목란.
"이미 찾은 설비"의 위치(Tag 글자 위치) 바로 위나 옆에 있는 기호는 그 설비다. 다시 적지 않는다.

각 항목: img(이미지 번호, 1부터), x·y(그 이미지 안 기호 중심, 0~1, 왼쪽 위 기준), what(짧은 영어 설명), ko(짧은 한국어 이름, 위치를 알 수 있게 예: "벨트 컨베이어 1 하부 이동식 컨테이너"), near(가장 가까운 설비 Tag, 없으면 ""), confidence(high|medium|low).
지어내지 않는다. 확실하지 않으면 confidence를 low로 한다. 없으면 items는 빈 배열.

출력은 JSON 하나만:
{{"items":[{{"img":1,"x":0.42,"y":0.61,"what":"wheeled solids skip under belt conveyor discharge","ko":"벨트 컨베이어 1 하부 이동식 컨테이너","near":"3200-CV-028","confidence":"high"}}]}}

## 이미 찾은 설비 (Tag|이름|x|y, 페이지 좌표 0~1)
{chr(10).join(known) or '-'}"""


def merge_vision(sh, boxes, items):
    """Tile points → page points; drop repeats across overlapping tiles, symbols already listed, and labels the text pass found."""
    out = []

    def near(a, b, d):
        return abs(a[0] - b[0]) < d and abs(a[1] - b[1]) < d
    tagged = [g["boxes"][t] for g in sh["eq"]["groups"] for t in g["tags"]]
    texts = [u["box"] for u in sh["eq"]["untagged"]]
    for it in items:
        k = js.number(it.get("img"))
        k = k if js.truthy(k) else 1
        b = boxes[int(k) - 1] if float(k).is_integer() and 1 <= k <= len(boxes) else None
        x, y = js.number(it.get("x")), js.number(it.get("y"))
        if not b or not js.finite(x) or not js.finite(y):
            continue
        pt = [b[0] + min(1, max(0, x)) * (b[2] - b[0]), b[1] + min(1, max(0, y)) * (b[3] - b[1])]
        if any(near(o["pt"], pt, 0.02) for o in out):
            continue
        if any(t[0] - 0.008 < pt[0] < t[2] + 0.008 and t[1] - 0.008 < pt[1] < t[3] + 0.008 for t in tagged):   # the point is a tag label itself
            continue
        if any(near([(t[0] + t[2]) / 2, (t[1] + t[3]) / 2], pt, 0.04) for t in texts):
            continue
        conf = it.get("confidence") if it.get("confidence") in ("high", "medium", "low") else "low"
        out.append({"pt": pt, "ko": js.cut(js.jstr(it.get("ko") or it.get("what") or "설비 기호"), 80), "what": js.cut(js.jstr(it.get("what") or ""), 120),
                    "near": js.jstr(it.get("near") or ""), "conf": conf,
                    "box": [max(0, pt[0] - 0.02), max(0, pt[1] - 0.02), min(1, pt[0] + 0.02), min(1, pt[1] + 0.02)]})
    return out
