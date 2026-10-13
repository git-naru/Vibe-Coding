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
