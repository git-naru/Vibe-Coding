# 인수인계 — PFD 공정 실적·투자비 산출

작성 2026-10-14 · 기준 `main` = PR #8 머지(`eb6a681`) 이후

이 문서는 로컬에서 새 프로젝트를 구성하고 작업을 이어 가기 위한 인수인계입니다. 요구사항과 결정 이력은 PRD에, 데이터 형식은 `.claude/skills/pfd-flow-viewer/references/data-schema.md`에 있습니다.

## 1. 한눈에 보기

PFD(Mass Balance 포함)를 읽어 공정 흐름도와 Equipment List를 만들고, 프로젝트별 실적(설비비·공사물량)을 쌓아, 새 프로젝트의 투자비(설비비 + 공사비)를 산출한다.

| 구성 | 위치 | 상태 |
|---|---|---|
| Claude Code 스킬 `pfd-flow-viewer` | `.claude/skills/pfd-flow-viewer/` | PFD → 흐름도 뷰어(Artifact). Python 스크립트 + 뷰어 템플릿 |
| HTML 앱 (공정 실적·투자비) | `apps/pfd-flow-viewer/app.html` (단일 파일, 약 3,200줄) | claude.ai Artifact로 게시해 사용 중 |
| PRD | claude.ai 문서 (링크는 2절) | F1~F50, 전환 계획 포함 |
| Python 핵심 로직 `pfdcore` | `core/` | PRD 전환 계획 1단계. 앱의 PDF 판독·Equipment List·설비비 매칭·투자비 산출·Excel 내려받기를 옮김. 가상 입력에서 앱 코드와 결과 동일 (`core/README.md`) |
| CI | `.github/workflows/ci.yml` | 스킬 스크립트·예제 뷰어, 앱 빌드·문법 검사, pfdcore 대조 테스트 |

## 2. 링크

| 항목 | 링크 | 비고 |
|---|---|---|
| 저장소 | https://github.com/git-naru/Vibe-Coding | 기본 브랜치 `main` |
| 공유 앱 (실데이터 없음) | https://claude.ai/artifact/1wpedHWdcjyZfR714mHFUf | 링크가 있으면 누구나 열람 |
| 비공개 앱 (실데이터 예시 포함) | https://claude.ai/artifact/EiW5GCr21ZyWsHP9thBbYd | 소유자만 열람 |
| PRD | https://claude.ai/code/artifact/803d79e1-ce3f-42f1-be0b-d8cceaa6ad81 | |

병합 이력: #1 스킬·HTML 앱·Equipment List·CI → #2 메인 흐름 탭·구역별 줄 배치·비공개 샘플 슬롯 → #3 실적/투자비 2분할·프로젝트 기록·상세설명 프레임·패키지 보기·설비비 매칭 → #4 투자비 산출 → #5 도면 번호 없는 시트 찾기 수정 → #6 인수인계 문서(HANDOVER.md·CLAUDE.md) → #7 로컬 `.venv`·`dist/` 무시(.gitignore) → #8 20MB 넘는 파일을 막지 않고 경고.

## 3. 저장소 구조

```
.claude/skills/pfd-flow-viewer/
  SKILL.md                    스킬 절차 (범위 → 읽기 → 정리 → 수지 검증 → 배치 → 빌드·게시 → 보고)
  scripts/pfd_extract.py      PDF 시트 식별, 시트 간 연결, Stream 검색, 렌더·크롭, XLSX/DOCX 덤프
  scripts/build_viewer.py     데이터 검증(참조·겹침·물질수지) 후 뷰어 HTML 빌드
  assets/viewer-template.html 스킬 뷰어 템플릿
  references/data-schema.md   흐름도 JSON, 탭 묶음, desc, packages, 프로젝트·기록·설비비·공사물량·단가 형식
  examples/demo-steam.json    가상 데이터 예제
apps/pfd-flow-viewer/
  app.html                    HTML 앱 원본 (__DEMO_DATA__, __SAMPLE_DATA__ 자리표시)
  build.py                    단일 HTML 빌드: 예제·한글 CMap 삽입, --sample 로 비공개 예시 삽입
  cmaps/                      pdf.js 3.11.174의 한글 CMap 24개(Adobe 라이선스). 빌드 때 #cmap-data로 들어감
  check_build.py              CI 검사: 자리표시 치환, sample-data가 null인지, 스크립트 추출
core/
  pfdcore/                    Python 패키지: pdf, sheets, streams, equipment, layout, cost, estimate, export, xlsx·ssf(SheetJS 읽기), js(JavaScript 동작)
  tests/                      앱 코드와 대조하는 테스트, 가상 입력 생성(fixtures.py), 실제 도면 대조 스크립트(compare_app.py)
  tests/parity/               harness.cjs: app.html 페이지 스크립트를 Node에서 실행 (pdf.js 3.11.174, SheetJS 0.18.5)
.github/workflows/ci.yml
README.md                     기능 설명(사용자 관점)
HANDOVER.md                   이 문서
CLAUDE.md                     Claude Code용 작업 규칙 요약
```

## 4. HTML 앱 구조 (`app.html`)

한 파일 안에 CSS, 마크업(화면 4개 + 대화상자), 스크립트가 있다. 외부 라이브러리는 jsdelivr CDN에서 필요할 때 불러온다: pdf.js 3.11.174, SheetJS 0.18.5, mammoth 1.8.0, dagre 0.8.5. pdf.js의 한글 CMap은 CDN에서 받지 않고 빌드 때 `#cmap-data`로 넣은 것을 `CMapReader`가 내준다(`openPdfDoc`).

화면: 시작(좌 "실적 입력" / 우 "투자비 산출" 2분할) → 실적 입력(프로젝트 목록) → 프로젝트 화면(공정 데이터 입력, 기록, Equipment List, 설비비 매칭, 공사물량, 흐름도, 상세설명 프레임) / 투자비 산출(산출 프로젝트, 공사 단가, 산출 기준). 산출 프로젝트도 같은 프로젝트 화면을 쓰고 "투자비 산출" 카드가 붙는다.

| 절 (코드 주석 번호) | 내용 | 주요 함수·상태 |
|---|---|---|
| 0 | 공통 도우미 | `$`, `esc`, `fmt`, `loadScript`, `CDN` |
| 1 | 도면 번호·시트 식별·시트 밖 연결 | `DWG_SRC`(…-PFD-…/…-PID-… 형식), `sheetIdentity`, `connectorsOf`, `buildLinks` |
| 2 | Stream Table 행 → 뷰어 항목 | `parseTextTable`, `parseXlsxTables` |
| 3 | 파일 읽기 (브라우저) | `readPdf`, `readXlsx`(설비비 목록 자동 인식), `readDocx`, `addFiles`, `finishEquipment` |
| 4 | Claude에 보낼 도면 조각 렌더 | 타일·크롭 |
| 5 | Claude 호출 | `ask`, `scopePrompt`, `topoPrompt`, `tablePrompt`, `descPrompt`/`describeFlow`; Area별 패키지 `packFlow`/`areaLabel`(Claude 호출 없음) |
| 6 | 생성 파이프라인 | `STEP_DEFS`, `buildFlow`, `generate`, `assemble`, `layout`(구역별 줄 배치), `linksOf`, `nodeInfoOf` |
| 7 | 뷰어 | `renderViewer`(흐름도 + 상세설명 카드), `showBundle`, `packageView`(패키지별 보기), `showView`, 탭 |
| 8 | 프로젝트·기록 저장 | `store`(db 또는 메모리), `saveRecord`(60,000자 part 분할), `openRecord`, `loadLegacy`, `importJson` |
| 10 | Equipment List, Layout·GA | `EQ`, `extractEquipment`, `buildEquipment`, `linkEquipmentToFlow`, `openPfd`, `pageImage`, `runVision`(그림 판독), `downloadEquipment`; Layout: `LAY`, `isLayoutSheet`, `layoutIndex`(Tag 맞춤), `renderLayout`/`drawLayout`, `layoutSelect`, `gotoRow`, `setFileRole`(파일 시트를 Layout↔PFD로) |
| 11 | 설비비 매칭 | `normTag`, `expandTags`, `parseCostWorkbook`, `computeCosts(C, rows)`, `costOfNodes`, `costAi` |
| 12 | 공사물량·투자비 산출 | `capOf`, `bundlePackages`, `resolveTarget`, `readQtyFile`, `RATES`/`EXP_DEFAULT`, `learnFrom`, `estEquipment`, `estQuantities`, `estCompute`, `downloadEstimate` |
| 9 | 화면 연결(마지막) | 버튼 핸들러, `openExample`, `adoptExample`, `go`(화면 이동) |

전역 상태: `S`(입력 파일·시트(`sheets` 공정, `layouts` Layout·GA)·결과 묶음·현재 프로젝트·기록 id), `EQ`(Equipment List·설비비 `cost`·공사물량 `qty`·산출 `est`), `P`(프로젝트·기록 목록), `RATES`(공사 단가·지수), `REF`(학습한 실적 캐시), `V`(지금 보이는 흐름도, 패키지 보기면 `.base`에 원본).

claude.ai capabilities: `{"sample": {"images": true}, "db": {}, "user": {}, "downloads": true}`. db는 `data/users/<id>` 아래 개인 저장(본인만 보임), 문서당 256 KiB 한도라 기록은 part 문서로 나눈다.

## 5. Claude 호출

| 프롬프트 표식 | 언제 | 횟수 |
|---|---|---|
| `[[SCOPE]]` | 생성 시작: 계통(메인 흐름) 범위·시트·Stream·라인 종류 | 탭당 1 |
| `[[TOPOLOGY 도면]]` | 시트마다 설비 간 연결 (도면 이미지 + 글자 위치) | 시트당 1 |
| `[[TABLE 도면]]` | Stream Table이 이미지인 시트의 표 판독 | 해당 시트당 1 |
| `[[DESCRIBE]]` | 설비·라인 역할 설명 (항목 70개 넘으면 설비/라인 나눠 2회) | 탭당 1~2 |
| `[[EQUIP-VISION 시트]]` | "그림으로 설비 찾기" (도면 4조각) | 시트당 1, 버튼 |
| `[[COST-MATCH]]` | 설비비 목록 중 Tag·이름으로 안 맞은 행 짝짓기 | 1, 버튼 |

모두 JSON 하나로 답하게 하고, 앱이 키·Tag를 검증해 없는 것은 버린다.

## 6. 빌드·검사·게시

```bash
python3 apps/pfd-flow-viewer/build.py dist/pfd-flow-app.html                      # 공유용 (예시는 가상 데이터)
python3 apps/pfd-flow-viewer/build.py dist/app-sample.html --sample sample.json    # 비공개용 (실데이터 예시 포함)
python3 apps/pfd-flow-viewer/check_build.py dist/app && node --check dist/app/app.js
python3 .claude/skills/pfd-flow-viewer/scripts/build_viewer.py --strict .claude/skills/pfd-flow-viewer/examples/demo-steam.json dist/demo.html
python3 -m pytest core/tests                                                      # pfdcore 대조 테스트 (11절 준비 참고)
```

게시는 Claude Code에서 Artifact로 올린다. 같은 링크를 갱신하려면 위 URL을 지정해 다시 올린다. 공유 앱에는 반드시 `--sample` 없이 빌드한 파일만 올린다.

비공개 예시 JSON 형식: `{label, note, project: {name, product, capacity, …, key}, bundle: {tabs: [...]}, equipment: {rows, refsMissing, areaNames, file, sheets}}`. `project`가 있으면 프로젝트 목록에 "예시" 카드로 나오고 "내 실적으로 가져오기"가 된다.

## 7. 보안 규칙 (지켜 온 것)

- 실제 프로젝트 데이터(도면, 도면 번호, Stream 값, 설비 목록, 설비비)는 저장소와 링크 공유 앱에 넣지 않는다. 저장소 예제는 가상 데이터만 쓴다.
- 실데이터 예시는 비공개 앱에만 넣는다. CI(`check_build.py`)가 저장소 빌드의 `sample-data`가 `null`인지 확인한다.
- 커밋 전에 diff에서 실데이터 흔적(고객사명, 실제 도면 번호 접두)을 검색한다.

## 8. 테스트

Playwright로 앱을 실제 브라우저에서 돌리는 테스트를 썼다. 실제 PDF와 실데이터를 쓰기 때문에 저장소에 넣지 않았고, 비공개 테스트 묶음(`private-testkit.zip`, 별도 전달)에 있다. 방식:

- CDN 요청을 로컬 `node_modules`의 같은 버전 파일로 돌린다 (`page.route`).
- `window.claude`를 가짜(`mock.js`)로 바꾼다: 프롬프트 표식별로 정해진 답, `db`는 `sessionStorage` 기반(where/orderBy, 256 KiB 한도 검사), `downloads`는 내려받은 바이트를 보관.
- 실행: `node apptest/<테스트>.js <작업 폴더> [PDF]`

| 테스트 | 확인 내용 |
|---|---|
| `projects.js` | 프로젝트 생성 → PDF 업로드 → 생성 → 자동 저장 → 새로고침 → 기록 다시 열기(Claude 0회) → 수정·삭제, 상세설명 프레임 스크롤 |
| `tabs.js` | 메인 + 계통 탭, 탭 추가, 저장·다시 열기, JSON 왕복 |
| `eqtest.js`, `vis.js` | Equipment List(진행률·10행·PFD 새 창·Excel), 그림으로 설비 찾기·중지·이어하기 |
| `layout.js`, `laycls.js` | Layout 카드 위치·Tag 맞춤(약식 Tag·목록에 없는 Tag)·선택·더블클릭 목록 이동·목록 클릭 선택·장 전환·Layout↔PFD 전환; 실제 PFD가 Layout으로 잘못 분류되지 않는지 |
| `packages.js`, `example.js` | Area별 패키지 생성·보기·설비 이동·다시 묶기, 손으로 그린 흐름도, 예시 프로젝트 가져오기 |
| `costs.js` | 설비비 목록 인식·Tag/이름/Claude/수동 매칭·직접 입력·Excel 대조 |
| `estimate.js` | 공사물량·단가·지수 → 산출(같은 PFD면 실적 그대로, 용량 ×2면 ×2^n)·직접 수정·저장 |
| `noscope.js` | 도면 번호 없는 시트: 파일·쪽으로 찾기, 메인 흐름 대체, 오류 문구 |
| `autolayout.js`, `sample.js` | 자동 배치 겹침·관통 0, 실적 샘플 보기 |

pfdcore 대조 테스트(`core/tests`)는 저장소 안에 있다. 가상 입력만 쓰고, 앱 코드(`app.html` 페이지 스크립트)를 Node에서 직접 실행해 결과를 비교한다. 실제 도면으로는 `python core/tests/compare_app.py 도면.pdf … --cost 설비비.xlsx`를 비공개 자료 폴더에서 돌린다(아무것도 저장하지 않음).

## 9. 알려진 한계

- 도면 번호는 `…-PFD-…`/`…-PID-…` 형식만 읽는다(다른 형식은 파일·쪽으로 대신 찾음). 스캔 PDF는 읽지 못한다(OCR 없음, PRD F13).
- 설비 연결은 Claude가 도면 이미지로 추정한다. 도면의 선(벡터)을 직접 읽지 않는다.
- PDF는 브라우저 메모리에 통째로 올려 읽는다. 크기 제한은 없지만 20MB가 넘는 파일은 경고를 띄우고(`BIG_FILE`), 아주 큰 파일은 탭이 멈출 수 있어 장 단위로 나눠 올리도록 안내한다.
- Layout·GA 도면은 글자 Tag 위치로만 맞춘다(그림만 있는 설비, 스캔본은 못 찾음). 도면 그림은 기록에 저장하지 않는다.
- 저장은 claude.ai 개인 저장소라 팀 공유·백업이 없고 원본 PDF를 보관하지 않는다.
- PDF 글꼴: 한글 CMap은 화면에 들어 있어(`cmaps/`, `CMapReader`) ToUnicode 없는 한글 CID 글꼴·KS 인코딩도 읽는다. 일본어·중국어(Adobe-Japan1/GB1/CNS1) CID 글꼴은 CMap이 없어 글자가 빠진다(다른 CMap은 불러오지 않음). 남은 앱 문제 두 가지(설비비 Tag 칸의 쉼표 뒤 다른 Area Tag, JSON 내려받기에 Equipment List·설비비가 빠짐)는 `core/README.md` 끝.
- 투자비: 지수 기본값은 일반 문헌의 대략값. 물가·지역 보정, 통화 환산, 간접비·예비비 없음. 실적의 설비비·물량이 일부만 있으면 물량이 크게 잡힐 수 있다. 실제 실적으로 검증하지 않았다.

## 10. 다음 단계

PRD "전환 계획: 사내 웹 서비스" 절을 따른다.

1. 핵심 로직 Python 분리 (PDF 판독, Equipment List, 설비비 매칭, 투자비 계산) + 테스트. 끝 조건: 지금 앱과 같은 입력에서 같은 결과. → `core/pfdcore` 완료, 가상 입력에서 같음. 남은 확인: 실제 도면으로 `compare_app.py`.
2. DB 설계(PostgreSQL)와 실적 이관 (앱에서 내려받은 JSON 가져오기).
3. FastAPI 서버 + 지금 화면 연결, 사내 시범 배포.
4. 정확도 개선: 도면 선 판독, OCR, 사람 수정값 학습, 실적 기반 지수 회귀.

전환 전에 정할 것: 사용 인원, 사내 서버·클라우드 허용, 도면 데이터의 외부 AI API 전송 허용, 유지보수 담당.

## 11. 로컬 새 프로젝트 구성 순서

1. 준비: Git, Python 3.10+(3.12 권장), Node 20(선택), Chrome/Edge, Claude Code. `pip install pillow openpyxl python-docx`, poppler(`pdftoppm`, `pdftotext`).
2. 코드 받기: `git clone https://github.com/git-naru/Vibe-Coding.git` (또는 새 저장소를 만들고 이 저장소 내용을 복사).
3. 스킬: 저장소 안 `.claude/skills/pfd-flow-viewer/`는 그 폴더에서 Claude Code를 열면 자동으로 잡힌다. 다른 프로젝트에서도 쓰려면 `pfd-flow-viewer-skill.zip`(별도 전달)을 `~/.claude/skills/`에 풀어 둔다.
4. 검사: `pip install -e "core[test]"`, `(cd core/tests/parity && npm ci)` 후 6절의 명령이 오류 없이 끝나는지 확인.
5. 비공개 자료: `private-testkit.zip`(실데이터 예시 JSON, 테스트 스크립트, 가짜 Claude, 가상 설비비·물량·단가 파일)은 저장소 밖 폴더에 풀고, 저장소에 넣지 않는다. 테스트에 쓰는 원본 PDF는 따로 보관 중인 파일을 같은 폴더에 둔다.
6. Claude Code를 저장소 폴더에서 열면 `CLAUDE.md`를 읽고 이 규칙대로 작업한다. 이어서 할 일은 10절 1단계.
