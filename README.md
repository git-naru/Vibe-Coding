# Vibe-Coding

## PFD Flow Viewer (Claude Code skill)

`.claude/skills/pfd-flow-viewer/` — PFD 도면과 Mass Balance(PDF, XLSX, DOCX)를 읽어 계통별 인터랙티브 흐름도를 만드는 Claude Code 스킬입니다.

- 이 저장소에서 Claude Code를 열고 PFD 파일을 첨부한 뒤 "스팀 계통 흐름도 그려줘"처럼 요청하면 스킬이 적용됩니다.
- 실제 프로젝트 데이터는 공개 저장소에 커밋하지 않습니다.
- 결과 화면: 계통 흐름도, 라인 클릭 시 Stream Table(유량·물성·성분), 설비 클릭 시 입출구 비교, 일 기준 물질수지 검증, 시트 간 불일치 표시.

| 경로 | 내용 |
|---|---|
| `SKILL.md` | 작업 절차 (범위 → 읽기 → 정리 → 수지 검증 → 배치 → 빌드·게시 → 보고) |
| `assets/viewer-template.html` | 고정된 화면 템플릿 (라이트/다크, 모바일 대응) |
| `scripts/pfd_extract.py` | PDF(여러 파일·여러 장) 시트 식별, 시트 간 연결 지도, Stream 번호 검색, 고해상도 렌더·표 크롭, XLSX/DOCX 덤프 |
| `scripts/build_viewer.py` | 데이터 검증(참조, 좌표 겹침, 물질수지) 후 HTML 빌드 |
| `references/data-schema.md` | 데이터 JSON 형식과 Stream Table 항목 매핑 |
| `examples/demo-steam.json` | 가상 데이터 예제: 보일러 1기, 사용처 3곳의 스팀 계통 |

직접 빌드:

```bash
cd .claude/skills/pfd-flow-viewer
python3 scripts/build_viewer.py examples/demo-steam.json /tmp/demo.html
```

필요 도구: Python 3, poppler-utils(`pdftoppm`, `pdftotext`, `pdfinfo`), Pillow, openpyxl, python-docx.

## PFD 흐름도 만들기 (HTML 앱)

`apps/pfd-flow-viewer/` — 같은 흐름도를 브라우저에서 만드는 단일 HTML 앱입니다(claude.ai Artifact로 게시).

- 업로드 버튼 → 파일 선택(PDF·XLSX·DOCX, 여러 파일·여러 장) → 그릴 계통 입력 → 생성.
- 브라우저: 파일 읽기(pdf.js, SheetJS, mammoth), 시트 식별·시트 간 연결, 텍스트·엑셀 표 값 채우기, 물질수지 검증, 자동 배치(dagre).
- Claude(`sample` capability): 계통 범위 판단 1회, 시트별 연결 해석(도면 이미지 + 글자 위치), 표가 이미지인 시트의 표 판독. 판독값은 "이미지 판독값"으로 표시됩니다.
- 결과는 개인 저장 목록(`db`, 본인만 보임)에 저장하거나 JSON으로 내려받고, 다시 열 때는 Claude를 부르지 않습니다.
- Equipment List: PDF를 올리면 Claude 없이 자동으로 만듭니다(원형 진행률 0~100%). 설비 이름 아래 단독으로 적힌 Tag를 설비로 보고, 호기 번호 분리·예비/향후 구분·도면 구역(테두리 격자 행-열)을 붙입니다. Tag 없이 이름만 있는 설비는 "미확인" 후보로 넣습니다.
  - 표는 10행 높이로 스크롤되고, 행을 더블클릭(또는 Enter)하면 해당 PFD 쪽을 새 창에 열어 위치를 빨간 상자로 표시합니다(새 창이 막히면 화면 안 보기).
  - 흐름도를 생성하거나 열면 그 계통 설비에 기준 Stream 값(유량·온도·압력)이 채워집니다.
  - "그림으로 설비 찾기"(F37): 글자 없이 기호로만 그려진 설비를 Claude가 도면 이미지(시트당 4조각, 1회 호출)로 찾아 "(그림)" 미확인 후보로 더합니다. 겹친 조각의 중복, Tag 글자 위치, 글자로 이미 찾은 후보는 걸러내고 신뢰도를 표시합니다. 중지 후 다시 누르면 남은 시트만 이어서 합니다.
  - "Excel로 내려받기"는 Equipment List, Summary, 도면 미포함 설비, 작성 기준 4개 시트의 .xlsx를 만듭니다.

```bash
python3 apps/pfd-flow-viewer/build.py /tmp/pfd-flow-app.html   # 예시 데이터를 넣어 단일 파일로 빌드
```

게시 시 capabilities: `{"sample": {"images": true}, "db": {}, "user": {}, "downloads": true}`

## CI

`.github/workflows/ci.yml` — PR과 `main` push마다 GitHub Actions가 돌립니다.

- 스킬: 스크립트 컴파일, 추출 CLI 로드, 가상 예제 뷰어 `--strict` 빌드(물질수지 검사 포함)
- HTML 앱: 빌드 후 예시 데이터 삽입 확인(`apps/pfd-flow-viewer/check_build.py`), 페이지 스크립트 `node --check` 문법 검사
