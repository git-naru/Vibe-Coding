# Viewer data schema

`scripts/build_viewer.py data.json out.html` injects this JSON into `assets/viewer-template.html`.
A complete, working example is `examples/demo-steam.json` (synthetic data) — copy it and replace the contents.

All text is shown as-is (escaped). Numbers are **strings copied exactly from the source**
(keep `1,562`, `4.5–5.5`, `NOTE 14`); an absent key means the source cell was blank / `-`.

```jsonc
{
  "meta": {
    "docTitle": "Demo 스팀 계통",                // <title>: 2–4 word name, no "– explainer"
    "eyebrow": "CLIENT · PROJECT · AREA 900",     // client · project · area
    "title": "스팀 생산·분배·응축수 회수 계통",     // page H1
    "lede": "어떤 도면을 묶어 그렸는지, 사용법 한 문장",
    "hint": "읽는 법 / 시간당 vs 일 합계 주의 등",   // shown under the diagram
    "diagramLabel": "스팀 계통 흐름도",
    "viewBox": [1620, 880],                       // SVG coordinate space
    "minWidth": 1100,                             // px; diagram scrolls sideways below this
    "defaultSelect": "110",                       // stream opened on first load
    "source": {"file": "…pdf", "pages": "27, 6, 9 …"} // provenance (not rendered, keep for rebuilds)
  },

  "categories": {                                 // line classes = legend entries (order = legend order)
    "steam10": {"label": "고압증기 10 bar(a)", "light": "#b02a1f", "dark": "#ff6f61"},
    "fuel":    {"label": "연료가스", "light": "#a07400", "dark": "#f0c04a", "dashed": true}
  },

  "checks": [                                     // mass-balance cards, computed in page + build script
    {"name": "헤더 증기 분배", "lhs": ["105"], "rhs": ["106","108","110","114"],
     "rhsLabel": "소비 106·108·110·114", "field": "dm", "unit": "t/d", "tol": 1}
  ],
  // or "balance": [{"k": "...", "v": "...", "ok": "...", "warn": false}] for hand-written cards

  "streams": {
    "110": {
      "cat": "steam4",
      "label": "110",                // optional badge text (default = key), e.g. "201a,b,c"
      "ko": "E-930 배치 반응기 가열 증기",            // Korean plain-language name
      "en": "Steam to batch reactor jacket",         // stream-table description, verbatim
      "from": "Steam Header (감압)", "to": "E-930",
      "sheet": "DEMO-900-PFD-001 · DEMO-930-PFD-001",
      "v": {                         // stream-table values, all optional
        "dm": "48",  "dv": "…",      // Balance (daily) mass t/d, volume m³/d
        "nm": "6.00","nv": "…",       // Nominal average t/h, m³/h
        "nxm": "6.00", "nxv": "…",     // Nominal maximum
        "nnm": "…", "nnv": "…",      // Nominal minimum
        "dsm": "7.20", "dsv": "…",     // Design average
        "dxm": "…", "dxv": "…",      // Design maximum
        "dnm": "…", "dnv": "…",      // Design minimum
        "rho": "…", "T": "143.6", "P": "4.0", "sol": "…", "liq": "…",
        "li": "…",                   // Li⁺ ppm (row hidden when absent)
        "pH": "…", "DF": "1.20", "RT": "8"
      },
      "extraProps": [["Concentration", "%", "29.58"]],   // any other "OTHER VALUES" rows
      "comp":       [["H₂O", "100"], ["Na⁺", "-"]],       // liquid composition, wt% (3rd item = unit override)
      "compSolids": [["Li₂CO₃", "99.98"]],                // solids composition
      "compNote": "증기 라인이라 도면에 액상 성분 값이 없습니다.",  // shown when no composition
      "kpi": [["Nominal", "606", "Nm³/h"]],               // override the 4 summary tiles
      "rows": [["Gas Flow (Nominal)", "Nm³/h", "606"]],   // free-form table for non-standard streams (gas, solids)
      "short": "가열 증기",                               // label used on node KPI tiles
      "note": ["Note 1: …", "930 시트에는 50 t/d로 적혀 있습니다."],
      "drawnAs": "101",              // highlight another stream's line when this one has none
      "info": true                   // unnumbered line: panel shows text only, hidden from chip list
    }
  },

  "nodes": [                         // equipment boxes (SVG coords, top-left + size)
    {"id": "HXC", "x": 1010, "y": 430, "w": 190, "h": 86,
     "title": "배치 반응기 재킷", "sub": "E-930", "sub2": "용액 40 → 90 °C",
     "sub2Strong": true,             // 3rd line in body weight (use for process-side summary)
     "src": true}                    // dashed grey box = battery limit / off-page source or destination
  ],

  "nodeInfo": {                      // panel content when a node (or bar) is clicked
    "HXC": {
      "title": "E-930 배치 반응기 재킷", "tags": "R-930 Jacket",
      "kpiStreams": ["110", "111"],  // tiles with nominal t/h, link to the stream
      "compare": {"title": "공정측 (피가열 유체)", "head": ["입구 221", "출구 222"],
                  "rows": [["Temperature", "°C", "40", "90"]],
                  "foot": ["221: Reactor charge"]},
      "info": ["설명 문단", "…"],
      "links": ["110", "111"]       // chips + highlight on the diagram
    }
  },

  "lines": [                         // polylines; arrow at the last point
    {"s": "110", "pts": [[940,460],[1010,460]], "lab": [975,460]},     // lab = badge centre
    {"s": "111", "pts": [[1200,492],[1260,492]], "lab": [1230,492], "arrow": false}, // joins a lane
    {"s": "dose", "pts": [[335,150],[335,230]], "dashed": true},
    {"s": null, "cat": "bfw", "pts": [[420,265],[480,265]]}           // decorative, not clickable
  ],
  "bars":   [{"x1":940,"y1":80,"x2":940,"y2":560,"cat":"steam10","node":"HDR",
              "label":"STEAM HEADER · 10 bar(a)","lx":928,"ly":420,"rotate":-90}],
  "dots":   [[1260,312]],            // junction dots
  "texts":  [{"x":700,"y":552,"t":"재순환"}],             // captions (cls: conn | ftitle, anchor, rotate)
  "frames": [{"x":1000,"y":56,"w":210,"h":480,"title":"STEAM USERS","tx":1010,"ty":556}]
}
```

## Field mapping from a typical stream table

| Stream-table row | key |
|---|---|
| BALANCE FLOW · Daily Mass / Volumetric Flow | `dm` / `dv` |
| NOMINAL FLOW · Mass / Volumetric (Average) | `nm` / `nv` |
| NOMINAL · Maximum / Minimum | `nxm` `nxv` / `nnm` `nnv` |
| DESIGN FLOW · Mass / Volumetric (Average) | `dsm` / `dsv` |
| DESIGN · Maximum / Minimum | `dxm` `dxv` / `dnm` `dnv` |
| Density, Temperature, Pressure (abs), % Solids, % Moisture/Liquid, Li⁺ ppm, pH, Design Factor, Run Time | `rho` `T` `P` `sol` `liq` `li` `pH` `DF` `RT` |
| Anything else (Concentration, Bulk density, Flow per batch, Number of maxibags …) | `extraProps` |
| CHEMICAL COMPOSITION – LIQUID / SOLIDS | `comp` / `compSolids` |
| Gas streams (Nm³/h), utilities with odd units | `rows` + `kpi` |

When a table has only one "Nominal" block (no average/max/min split), use `nm`/`nv`.
