# 구현 작업 체크리스트

> 설계 근거는 [DESIGN.md](./DESIGN.md) 참고. 목표는 학습용 문서 생성기: 주제 → 목차 → 섹션별 심화 리서치 → 조립된 학습 문서. codex가 아래 순서대로 구현.

## Phase 0 — 프로젝트 뼈대
- [ ] `pyproject.toml` 작성 (의존성: `mcp`, `gpt-researcher`, `python-dotenv`, `pydantic`, `httpx` 등), Python 버전 고정
- [ ] `.gitignore` 작성 (`.env`, `__pycache__/`, `outputs/`, `.venv/`, `*.pyc`)
- [ ] `.env.example` 작성 (DESIGN.md 8장 내용 반영)
- [ ] `mcp_server/` 패키지 스켈레톤 생성 (`__init__.py`, `server.py`, `toc.py`, `research.py`, `assemble.py`, `config.py`, `schemas.py`, `storage.py`)

## Phase 1 — SearXNG 로컬 구동
- [ ] `docker-compose.yml` 작성: SearXNG + Redis, `127.0.0.1:8080`에만 포트 바인딩
- [ ] `searxng/settings.yml` 작성: `search.formats`에 `json` 추가, `SEARXNG_SECRET` 환경변수로 주입
- [ ] `docker compose up -d` 로 기동 후 `curl 'http://localhost:8080/search?q=test&format=json'` 정상 응답 확인

## Phase 2 — 저장소 레이어 (storage.py)
- [ ] `outputs/<topic-slug>/` 디렉터리 구조 생성 함수 (DESIGN.md 6장)
- [ ] `manifest.json` 읽기/쓰기 (topic, created_at, depth, 섹션별 status/timestamp/source_count)
- [ ] topic → slug 변환 함수 (파일시스템 안전한 slugify)
- [ ] 섹션 id → 파일명 매핑 함수 (`sections/01-<slug>.md` 형식)

## Phase 3 — 목차 생성 (toc.py, `generate_toc` 도구)
- [ ] LLM 호출로 주제 → 목차(섹션 + 하위섹션 + 설명) 생성 로직
- [ ] `depth`(standard/deep), `num_sections` 힌트 반영
- [ ] 결과를 `toc.json`(구조화) + `toc.md`(가독용)로 저장
- [ ] `manifest.json`에 섹션 목록을 `pending` 상태로 초기화

## Phase 4 — 섹션별 심화 리서치 (research.py, `research_section` 도구)
- [ ] `config.py`: `.env` 로드, 필수 값(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, `SEARXNG_URL`) 검증
- [ ] `GPTResearcher` 래퍼: `RETRIEVER=searxng` 강제, 섹션 제목+설명을 쿼리로 사용
- [ ] 형제 섹션(같은 목차의 다른 섹션 제목/설명)을 컨텍스트로 전달해 중복 방지
- [ ] `force=false`일 때 이미 `done` 상태인 섹션은 재실행하지 않고 기존 결과 반환
- [ ] 결과(`content_markdown`, `sources`)를 `sections/<id>-<slug>.md`에 저장, `manifest.json` 상태를 `done`으로 갱신
- [ ] `quick_search()` 함수: SearXNG JSON API 직접 호출 (GPT-Researcher 우회), 상위 N개 결과 반환

## Phase 5 — 문서 조립 (assemble.py)
- [ ] `toc.json` 순서대로 `sections/*.md`를 읽어 하나의 `study_document.md`로 병합 (섹션 제목을 헤딩으로, 전체 상단에 목차/링크 포함)
- [ ] 아직 리서치 안 된(`pending`) 섹션이 있으면 조립 결과에 명시적으로 표시 (누락 아님을 알 수 있게)

## Phase 6 — MCP 서버 (server.py)
- [ ] `mcp_server/schemas.py`: `generate_toc`, `research_section`, `build_study_document`, `quick_search` 입출력 pydantic 스키마 (DESIGN.md 7장)
- [ ] 4개 tool 등록 및 핸들러 연결 (stdio transport, `mcp` Python SDK)
- [ ] `build_study_document`: TOC 없으면 `generate_toc` 먼저 호출 → `sections_filter` 또는 전체 미완료 섹션 순회하며 `research_section` 호출 → `assemble` 호출
- [ ] `build_study_document` 진행 중 섹션마다 progress notification 전송 ("N/총 섹션 완료: <제목>")
- [ ] 에러 처리: SearXNG 연결 실패, LLM API 키 누락/오류, 잘못된 `section_id`, 타임아웃 — 명확한 에러 메시지로 반환
- [ ] 서버 단독 실행 스모크 테스트 (stdio로 tool list 조회 확인)

## Phase 7 — 클라이언트 연동 설정
- [ ] Claude Code용 `.mcp.json` 예시 파일 작성
- [ ] Codex CLI용 `~/.codex/config.toml` 스니펫을 README/`docs/`에 예시로 포함 (실제 사용자 config는 건드리지 않음)
- [ ] 실제 Claude Code CLI에서 `claude mcp add`로 등록 후 4개 도구 모두 호출 테스트
- [ ] 실제 Codex CLI에서 동일 테스트

## Phase 8 — 테스트 & 문서
- [ ] `tests/test_toc.py`: 목차 생성 결과 스키마 검증 (mock LLM 또는 실제 소규모 호출)
- [ ] `tests/test_research.py`: `quick_search` 유닛 테스트, config 검증 로직(API 키 누락 시 에러) 테스트
- [ ] `tests/test_assemble.py`: 섹션 일부만 완료된 상태에서 조립 시 pending 표시 확인
- [ ] README.md 업데이트: 프로젝트 한 줄 소개 + 설치/실행 개요 (단, **`docs/setup.md` 상세 사용법 문서 자체는 작성하지 말 것** — Claude가 이후 작성/검토)

## Phase 9 — 커밋 규율
- [ ] Phase 단위(혹은 논리적 단위)로 커밋 분리, 커밋 메시지는 무엇을·왜 했는지 명확히
- [ ] `.env` 등 시크릿 파일이 커밋에 포함되지 않았는지 `git status`/`git diff --cached`로 확인 후 push

---

## 완료 후 Claude가 담당할 작업 (codex 작업 범위 아님)
- [ ] 구현 코드 리뷰 (`/code-review`)
- [ ] 실사용 검증 (실제 과목/주제로 `build_study_document` 끝까지 실행해 결과물 품질 확인)
- [ ] `docs/setup.md` 사용법 문서 작성
- [ ] (향후, 별도 설계) 오디오 오버뷰 파이프라인 설계
