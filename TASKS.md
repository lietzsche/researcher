# 구현 작업 체크리스트

> 설계 근거는 [DESIGN.md](./DESIGN.md) 참고. 목표는 학습용 문서 생성기: 주제 → 목차 → 섹션별 심화 리서치 → 조립된 학습 문서. codex가 아래 순서대로 구현.

## Phase 0 — 프로젝트 뼈대
- [x] `pyproject.toml` 작성 (의존성: `mcp`, `gpt-researcher`, `python-dotenv`, `pydantic`, `httpx` 등), Python 버전 고정
- [x] `.gitignore` 작성 (`.env`, `__pycache__/`, `outputs/`, `.venv/`, `*.pyc`)
- [x] `.env.example` 작성 (DESIGN.md 8장 내용 반영)
- [x] `mcp_server/` 패키지 스켈레톤 생성 (`__init__.py`, `server.py`, `toc.py`, `research.py`, `assemble.py`, `config.py`, `schemas.py`, `storage.py`)

## Phase 1 — SearXNG 로컬 구동
- [x] `docker-compose.yml` 작성: SearXNG + Redis, `127.0.0.1:8080`에만 포트 바인딩
- [x] `searxng/settings.yml` 작성: `search.formats`에 `json` 추가, `SEARXNG_SECRET` 환경변수로 주입
- [x] `docker compose up -d` 로 기동 후 `curl 'http://localhost:8080/search?q=test&format=json'` 정상 응답 확인

## Phase 2 — 저장소 레이어 (storage.py)
- [x] `outputs/<topic-slug>/` 디렉터리 구조 생성 함수 (DESIGN.md 6장)
- [x] `manifest.json` 읽기/쓰기 (topic, created_at, depth, 섹션별 status/timestamp/source_count)
- [x] topic → slug 변환 함수 (파일시스템 안전한 slugify)
- [x] 섹션 id → 파일명 매핑 함수 (`sections/01-<slug>.md` 형식)

## Phase 3 — 목차 생성 (toc.py, `generate_toc` 도구)
- [x] LLM 호출로 주제 → 목차(섹션 + 하위섹션 + 설명) 생성 로직
- [x] `depth`(standard/deep), `num_sections` 힌트 반영
- [x] 결과를 `toc.json`(구조화) + `toc.md`(가독용)로 저장
- [x] `manifest.json`에 섹션 목록을 `pending` 상태로 초기화

## Phase 4 — 섹션별 심화 리서치 (research.py, `research_section` 도구)
- [x] `config.py`: `.env` 로드, 필수 값(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, `SEARXNG_URL`) 검증
- [x] `GPTResearcher` 래퍼: `RETRIEVER=searxng` 강제, 섹션 제목+설명을 쿼리로 사용
- [x] 형제 섹션(같은 목차의 다른 섹션 제목/설명)을 컨텍스트로 전달해 중복 방지
- [x] `force=false`일 때 이미 `done` 상태인 섹션은 재실행하지 않고 기존 결과 반환
- [x] 결과(`content_markdown`, `sources`)를 `sections/<id>-<slug>.md`에 저장, `manifest.json` 상태를 `done`으로 갱신
- [x] `quick_search()` 함수: SearXNG JSON API 직접 호출 (GPT-Researcher 우회), 상위 N개 결과 반환

## Phase 5 — 문서 조립 (assemble.py)
- [x] `toc.json` 순서대로 `sections/*.md`를 읽어 하나의 `study_document.md`로 병합 (섹션 제목을 헤딩으로, 전체 상단에 목차/링크 포함)
- [x] 아직 리서치 안 된(`pending`) 섹션이 있으면 조립 결과에 명시적으로 표시 (누락 아님을 알 수 있게)

## Phase 6 — MCP 서버 (server.py)
- [x] `mcp_server/schemas.py`: `generate_toc`, `research_section`, `build_study_document`, `quick_search` 입출력 pydantic 스키마 (DESIGN.md 7장)
- [x] 4개 tool 등록 및 핸들러 연결 (stdio transport, `mcp` Python SDK)
- [x] `build_study_document`: TOC 없으면 `generate_toc` 먼저 호출 → `sections_filter` 또는 전체 미완료 섹션 순회하며 `research_section` 호출 → `assemble` 호출
- [x] `build_study_document` 진행 중 섹션마다 progress notification 전송 ("N/총 섹션 완료: <제목>")
- [x] 에러 처리: SearXNG 연결 실패, LLM API 키 누락/오류, 잘못된 `section_id`, 타임아웃 — 명확한 에러 메시지로 반환
- [x] 서버 단독 실행 스모크 테스트 (stdio로 tool list 조회 확인)

## Phase 7 — 클라이언트 연동 설정
- [x] Claude Code용 `.mcp.json` 예시 파일 작성
- [x] Codex CLI용 `~/.codex/config.toml` 스니펫을 README/`docs/`에 예시로 포함 (실제 사용자 config는 건드리지 않음)
- [x] 실제 Claude Code CLI에서 `claude mcp add`로 등록 후 4개 도구 모두 호출 테스트
- [x] 실제 Codex CLI에서 동일 테스트

## Phase 8 — 테스트 & 문서
- [x] `tests/test_toc.py`: 목차 생성 결과 스키마 검증 (mock LLM 또는 실제 소규모 호출)
- [x] `tests/test_research.py`: `quick_search` 유닛 테스트, config 검증 로직(API 키 누락 시 에러) 테스트
- [x] `tests/test_assemble.py`: 섹션 일부만 완료된 상태에서 조립 시 pending 표시 확인
- [x] README.md 업데이트: 프로젝트 한 줄 소개 + 설치/실행 개요 (단, **`docs/setup.md` 상세 사용법 문서 자체는 작성하지 말 것** — Claude가 이후 작성/검토)

## Phase 9 — 커밋 규율
- [x] Phase 단위(혹은 논리적 단위)로 커밋 분리, 커밋 메시지는 무엇을·왜 했는지 명확히
- [x] `.env` 등 시크릿 파일이 커밋에 포함되지 않았는지 `git status`/`git diff --cached`로 확인 후 push

## Phase 10 — DeepSeek 프로바이더 전환 (DESIGN.md 12장)

> Phase 0-9는 완료됨. 이 phase는 Anthropic/OpenAI 기본값을 DeepSeek로 바꾸는 후속 변경.

- [x] 설치된 `gpt-researcher` 버전 소스/문서에서 `deepseek` 프로바이더 문자열(`deepseek:deepseek-v4-flash` 등)이 실제로 인식되는지 확인 (LiteLLM 경유 여부 포함)
  - [x] 인식되면: 그대로 사용
  - [x] 인식되지 않으면: DeepSeek의 OpenAI 호환 엔드포인트(`https://api.deepseek.com`)로 폴백 — 해당 없음: 0.16.0의 native `deepseek` provider가 같은 엔드포인트를 직접 사용함
- [x] `mcp_server/config.py`: `Settings`에 `deepseek_api_key` 필드 추가, `validate_provider_and_retriever`가 `anthropic_api_key`/`openai_api_key`/`deepseek_api_key` 중 하나만 있어도 통과하도록 수정
- [x] `load_settings()`가 `DEEPSEEK_API_KEY` 환경변수를 읽도록 수정
- [x] `.env.example`: DESIGN.md 8장 예시대로 DeepSeek를 기본값으로, Anthropic/OpenAI는 주석 처리된 대체 옵션으로 갱신
- [x] `README.md`: 요구 사항 문구를 "Anthropic 또는 OpenAI API 키"에서 "DeepSeek(기본) 또는 Anthropic/OpenAI API 키"로 갱신
- [x] `tests/test_research.py` 등 config 검증 테스트에 DeepSeek 키만 있는 케이스 추가
- [x] `STRATEGIC_LLM`은 `deepseek:deepseek-v4-pro`, `FAST_LLM`/`SMART_LLM`은 `deepseek:deepseek-v4-flash` 기본값으로 설정
- [x] 실제 `DEEPSEEK_API_KEY`로 `generate_toc` 최소 1회 실행해 정상 응답 확인 (2026-07-26 `deepseek:deepseek-v4-pro` 및 `deepseek:deepseek-v4-flash`, 각각 2개 섹션과 `toc.json`/`toc.md`/`manifest.json` 검증)

---

## 완료 후 Claude가 담당할 작업 (codex 작업 범위 아님)
- [ ] 구현 코드 리뷰 (`/code-review`)
- [ ] 실사용 검증 (실제 과목/주제로 `build_study_document` 끝까지 실행해 결과물 품질 확인)
- [ ] `docs/setup.md` 사용법 문서 작성
- [ ] (향후, 별도 설계) 오디오 오버뷰 파이프라인 설계
