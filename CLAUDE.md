# CLAUDE.md

PFD(Mass Balance 포함)로 공정 흐름도·Equipment List를 만들고, 프로젝트별 실적(설비비·공사물량)을 쌓아 투자비를 산출하는 프로젝트. 전체 인수인계는 `HANDOVER.md`, 데이터 형식은 `.claude/skills/pfd-flow-viewer/references/data-schema.md`.

## 규칙

- 실제 프로젝트 데이터(도면, 실제 도면 번호, Stream 값, 설비 목록, 설비비)는 저장소·공개 링크에 넣지 않는다. 예제와 테스트 데이터는 가상으로 만든다. 커밋 전에 diff에서 고객사명·실제 도면 번호 흔적을 검색한다.
- `apps/pfd-flow-viewer/build.py`의 `--sample`(실데이터 예시)은 비공개 빌드에만 쓴다. CI가 저장소 빌드의 `sample-data`가 `null`인지 확인한다.
- 앱(`apps/pfd-flow-viewer/app.html`)은 한 파일이다. 주변 코드의 밀도·이름 짓기·주석 습관을 따른다. 화면 문구는 한국어.
- 기능을 바꾸면 README와 data-schema(형식이 바뀌면)를 함께 고친다.

## 검사 (CI와 같음)

```bash
python -m py_compile .claude/skills/pfd-flow-viewer/scripts/*.py apps/pfd-flow-viewer/*.py
python .claude/skills/pfd-flow-viewer/scripts/pfd_extract.py --help > /dev/null
python .claude/skills/pfd-flow-viewer/scripts/build_viewer.py --strict .claude/skills/pfd-flow-viewer/examples/demo-steam.json dist/demo.html
python apps/pfd-flow-viewer/check_build.py dist/app && node --check dist/app/app.js
```

## 지금 진행 중

PRD "전환 계획: 사내 웹 서비스" 1단계 — 핵심 로직(PDF 판독, Equipment List, 설비비 매칭, 투자비 계산)을 Python 패키지로 분리하고, 지금 앱과 같은 결과가 나오는지 테스트로 확인.
