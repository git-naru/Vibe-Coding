# CLAUDE.md

PFD(Mass Balance 포함)로 공정 흐름도·Equipment List를 만들고, 프로젝트별 실적(설비비·공사물량)을 쌓아 투자비를 산출하는 프로젝트. 전체 인수인계는 `HANDOVER.md`, 데이터 형식은 `.claude/skills/pfd-flow-viewer/references/data-schema.md`.

## 규칙

- 실제 프로젝트 데이터(도면, 실제 도면 번호, Stream 값, 설비 목록, 설비비)는 저장소·공개 링크에 넣지 않는다. 예제와 테스트 데이터는 가상으로 만든다. 커밋 전에 diff에서 고객사명·실제 도면 번호 흔적을 검색한다.
- `apps/pfd-flow-viewer/build.py`의 `--sample`(실데이터 예시)은 비공개 빌드에만 쓴다. CI가 저장소 빌드의 `sample-data`가 `null`인지 확인한다.
- 앱(`apps/pfd-flow-viewer/app.html`)은 한 파일이다. 주변 코드의 밀도·이름 짓기·주석 습관을 따른다. 화면 문구는 한국어.
- 기능을 바꾸면 README와 data-schema(형식이 바뀌면)를 함께 고친다.
- `app.html`의 핵심 로직(1~3절 읽기, 10절 Equipment List, 11절 설비비, 12절 투자비)을 바꾸면 `core/pfdcore`의 같은 함수도 고친다. `core/tests`의 대조 테스트가 앱 코드를 직접 돌려 비교하므로, 앱만 고치면 CI가 실패한다.

## 검사 (CI와 같음)

```bash
python -m py_compile .claude/skills/pfd-flow-viewer/scripts/*.py apps/pfd-flow-viewer/*.py
python .claude/skills/pfd-flow-viewer/scripts/pfd_extract.py --help > /dev/null
python .claude/skills/pfd-flow-viewer/scripts/build_viewer.py --strict .claude/skills/pfd-flow-viewer/examples/demo-steam.json dist/demo.html
python apps/pfd-flow-viewer/check_build.py dist/app && node --check dist/app/app.js
python -m pytest core/tests   # pip install -e "core[test]", (cd core/tests/parity && npm ci) 먼저
```

## 지금 진행 중

PRD "전환 계획: 사내 웹 서비스" 1단계 — 핵심 로직을 `core/pfdcore`로 옮겼고, 가상 입력에서는 앱 코드와 결과가 같다(`core/README.md`). 남은 일: 비공개 실제 도면으로 `python core/tests/compare_app.py`를 돌려 차이를 확인. 그다음 2단계(DB 설계·실적 이관). 옮기면서 찾은 앱 문제 중 한글 글자 누락은 고쳤고, 남은 두 가지는 `core/README.md` 끝에 있다.
