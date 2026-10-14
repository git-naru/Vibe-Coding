# pfdcore — 핵심 로직 Python 패키지

PRD "전환 계획: 사내 웹 서비스" 1단계. `apps/pfd-flow-viewer/app.html`의 핵심 로직(PDF 판독, Equipment List, 설비비 매칭, 공사물량·투자비 산출, Excel 내려받기)을 Python으로 옮겼다. 같은 입력에서 앱과 같은 결과가 나오는지 앱의 코드를 직접 돌려 대조하는 테스트로 확인한다. 데이터 형식은 앱의 기록 형식(`data-schema.md`) 그대로라 앱 기록을 그대로 읽고 쓸 수 있다.

## 설치

```bash
pip install -e "core[test]"          # Python 3.10+ (pdfminer.six, openpyxl, pytest)
(cd core/tests/parity && npm ci)     # 대조 테스트용: 앱이 쓰는 pdf.js 3.11.174, SheetJS 0.18.5 (Node 20)
python -m pytest core/tests
```

## 쓰기

```bash
pfdcore equipment A.pdf B.pdf --cost 설비비.xlsx --xlsx equipment-list.xlsx --json equipment.json   # --layout GA.pdf / --pfd X.pdf 로 파일 역할 지정
pfdcore estimate --rows 산출.json --record "실적 A=a.json" --record "실적 B=b.json" --rates 단가.xlsx --xlsx estimate.xlsx
```

`estimate`의 JSON은 앱 기록 형식 `{bundle, equipment: {rows, cost}, qty, est}`이다.

```python
import pfdcore
sheets = pfdcore.read_pdf("A.pdf")                       # 시트마다 글자 항목·도면 번호·연결·설비
eq = pfdcore.build_equipment(sheets)                     # {rows, refsMissing, areaNames}
lst = pfdcore.parse_cost_workbook(pfdcore.read_workbook("설비비.xlsx"))
C = pfdcore.load_cost_list(None, lst, "설비비.xlsx")
K = pfdcore.compute_costs(C, eq["rows"])                 # 설비별 설비비, 매칭 방법, 합계
```

## 모듈과 앱 코드의 대응

| 모듈 | app.html 절 | 내용 |
|---|---|---|
| `pdf` | 3 `readPdf` | pdf.js 글자 항목 규칙을 그대로 재현 (글리프 위치 비교, 가짜 공백, 줄·간격으로 나누기, q가 글자 상태까지 복사, Form XObject), 이미지 영역, 페이지 회전 |
| `sheets` | 1 | 도면 번호, 시트 식별, 시트 밖 연결, 시트 간 연결 대조 |
| `streams` | 2 | Stream Table (텍스트 레이어·XLSX) → 뷰어 항목 |
| `equipment` | 10 | 설비 판별, Equipment List, 흐름도 Stream 값 연결, 그림 판독 결과 합치기 |
| `layout` | 10 뒤 Layout | Layout·GA 도면 가려내기(파일별 전환 포함), 도면 위 Tag → Equipment List 행 연결 |
| `cost` | 11 | 설비비 목록 읽기, Tag·이름·Claude·수동 매칭, 직접 입력 |
| `estimate` | 12 | 공사물량·단가 읽기, 실적 학습, 설비비(용량지수·실적 단가)·공사비 산출 |
| `export` | 10·12 내려받기 | Equipment List·투자비 근거 Excel (시트·칸 동일) |
| `xlsx`, `ssf` | SheetJS | 엑셀을 SheetJS와 같게 읽기 (사용 범위, 빈 행, 날짜는 일련번호, General 표시 형식) |
| `js` | — | 앱 결과가 기대는 JavaScript 동작 (반올림, 숫자→글자, 정규식, ICU 정렬, 객체 키 순서, 순차 덧셈) |

## 같은 결과 확인

`tests/parity/harness.cjs`가 `app.html`의 페이지 스크립트를 Node에서 그대로 실행한다(화면은 가짜, pdf.js·SheetJS는 앱과 같은 버전). 테스트는 같은 가상 입력(`tests/fixtures.py`: 가짜 PFD PDF, 설비비·물량·단가 Excel)을 앱 코드와 pfdcore에 넣고 결과 JSON을 비교한다. 소수는 상대 오차 1e-12까지 같다고 본다(`Math.pow`·`Math.log` 마지막 자리 차이). 대조 대상: 글자 항목·이미지 영역, 시트 기록, 시트 연결, Equipment List, Stream 값 연결, Layout·GA 도면 가려내기와 Tag 위치, 설비비 목록·매칭(5가지 경우), Claude 매칭 검증, 공사물량·단가 읽기, 산출(5가지 경우), Excel 두 가지(모든 칸), SheetJS 읽기(21개 표시 형식 × 23개 값, CSV).

실제 도면은 저장소에 넣지 않으므로 비공개 자료로 따로 대조한다.

```bash
python core/tests/compare_app.py 실제도면1.pdf 실제도면2.pdf --cost 설비비.xlsx
```

## 앱과 다를 수 있는 곳

- 엑셀 표시 형식: General과 흔한 숫자 형식(0, 0.00, #,##0.0, %, 천 단위 나눔, 따옴표 글자)만 SheetJS와 같게 쓴다. 날짜·분수·지수 형식은 General로 쓰고 `ssf.unsupported`에 남긴다. 이 글자는 XLSX Stream Table에만 쓰이고 Equipment List·설비비·투자비 계산은 원래 값으로 한다.
- `.xls`(구 Excel)는 읽지 않는다. `.xlsx`, `.csv`만 읽는다.
- PDF: 세로쓰기, 오른쪽→왼쪽 글자, 주석(annotation) 안 이미지, pdf.js가 작은 반복 이미지를 묶는 경우는 재현하지 않는다(시트 `warnings`에 표시).
- `cmap_fonts="read"`로 CMap 글꼴을 읽을 때 CID→유니코드 표는 pdfminer 것이라 드문 CID에서 pdf.js와 다를 수 있다.

## 옮기면서 찾은 앱 문제 (앱은 고치지 않았고, pfdcore는 앱과 같게 동작)

1. pdf.js에 `cMapUrl`을 주지 않아, CMap 파일이 필요한 글꼴(ToUnicode 없는 Adobe-Korea1/Japan1/GB1/CNS1 CID 글꼴, UniKS-UCS2-H 같은 미리 정의된 인코딩)의 글자가 통째로 빠진다. 한글 설비명이 이런 글꼴이면 Equipment List에 나오지 않는다. 고치려면 `getDocument`에 `cMapUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/cmaps/', cMapPacked: true`를 넣는다. pfdcore는 `read_pdf(cmap_fonts="read")`로 고친 뒤의 결과를 낸다.
2. `expandTags("3200-PU-001~003, 4100-AG-002A/B")`가 쉼표 뒤 `4100`을 번호로 읽어 `3200-PU-4100`을 만들고 `4100-AG-002A/B`를 놓친다. 설비비 목록 Tag 칸에 Area가 다른 Tag를 쉼표로 이어 쓰면 매칭이 틀린다.
3. "JSON 내려받기"는 흐름도 묶음만 내려받고 Equipment List·설비비·공사물량·산출 선택은 빠진다. 2단계(실적 이관)에는 기록 전체(`{bundle, equipment, qty, est}`)를 내려받는 기능이 필요하다.
