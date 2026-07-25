# 구현 작업 체크리스트

> 설계 근거는 [DESIGN.md](./DESIGN.md) 참고. 이 체크리스트는 codex가 순서대로 구현.

## Phase 0 — 프로젝트 뼈대
- [ ] `pyproject.toml` 작성 (의존성: `mcp`, `gpt-researcher`, `python-dotenv`, `pydantic` 등), Python 버전 고정
- [ ] `.gitignore` 작성 (`.env`, `__pycache__/`, `outputs/`, `.venv/`, `*.pyc`)
- [ ] `.env.example` 작성 (DESIGN.md 7장 내용 반영)
- [ ] `mcp_server/` 패키지 스켈레톤 생성 (`__init__.py`, `server.py`, `research.py`, `config.py`, `schemas.py`)

## Phase 1 — SearXNG 로컬 구동
- [ ] `docker-compose.yml` 작성: SearXNG + Redis, `127.0.0.1:8080`에만 포트 바인딩 (외부 노출 금지)
- [ ] `searxng/settings.yml` 작성: `search.formats`에 `json` 추가, `SEARXNG_SECRET` 환경변수로 주입
- [ ] `docker compose up -d` 로 기동 후 `curl 'http://localhost:8080/search?q=test&format=json'` 정상 응답 확인
- [ ] SearXNG 컨테이너 재시작 시 설정 유지되는지 확인 (볼륨 마운트)

## Phase 2 — GPT-Researcher 연동
- [ ] `mcp_server/config.py`: `.env` 로드, 필수 값(`ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY`, `SEARXNG_URL`) 검증 로직
- [ ] `mcp_server/research.py`: `GPTResearcher` 인스턴스 생성 래퍼 함수
  - [ ] `RETRIEVER=searxng` 환경변수로 SearXNG 사용 강제
  - [ ] `report_type`, `max_sources`(source 개수 제한 파라미터로 매핑), `focus_domains` 옵션 반영
  - [ ] 리서치 결과에서 `report`, `sources`(제목/URL 목록) 추출
  - [ ] `outputs/` 디렉터리에 보고서 파일 저장 (파일명: 타임스탬프 + slugified query)
- [ ] `mcp_server/research.py`: SearXNG 직접 호출하는 `quick_search()` 함수 (GPT-Researcher 우회, httpx로 JSON API 직접 조회)

## Phase 3 — MCP 서버
- [ ] `mcp_server/schemas.py`: `deep_research`, `quick_search` 입출력 pydantic 스키마 정의 (DESIGN.md 5장)
- [ ] `mcp_server/server.py`: MCP stdio 서버 구현 (`mcp` Python SDK 사용)
  - [ ] `deep_research` tool 등록 및 핸들러 연결
  - [ ] `quick_search` tool 등록 및 핸들러 연결
  - [ ] `deep_research` 실행 중 단계별 progress notification 전송 (검색/수집/작성/완료)
  - [ ] 에러 처리: SearXNG 연결 실패, LLM API 키 누락/오류, 타임아웃 시 사용자에게 명확한 에러 메시지 반환
- [ ] 서버 단독 실행 스모크 테스트 (`python mcp_server/server.py` 로 기동 후 stdio로 tool list 조회 확인)

## Phase 4 — 클라이언트 연동 설정
- [ ] Claude Code용 `.mcp.json` 예시 파일 작성 (프로젝트 루트 또는 `docs/` 하위)
- [ ] Codex CLI용 `~/.codex/config.toml` 스니펫을 `docs/` 또는 README에 예시로 포함 (실제 사용자 config는 건드리지 않음)
- [ ] 실제 Claude Code CLI에서 `claude mcp add`로 등록 후 `deep_research`/`quick_search` 호출 테스트
- [ ] 실제 Codex CLI에서 동일 테스트

## Phase 5 — 테스트 & 문서
- [ ] `tests/test_research.py`: `quick_search` 최소 유닛 테스트 (SearXNG mock 또는 로컬 인스턴스 대상 통합 테스트)
- [ ] `tests/test_research.py`: config 검증 로직 유닛 테스트 (API 키 누락 시 명확한 에러)
- [ ] README.md 업데이트: 프로젝트 한 줄 소개 + 설치 링크(docs/setup.md 참조)는 codex가 작성, 단 **`docs/setup.md` 상세 사용법 문서 자체는 작성하지 말 것** — 이후 Claude가 작성/검토 예정

## Phase 6 — 커밋 규율
- [ ] Phase 단위(혹은 논리적 단위)로 커밋 분리, 커밋 메시지는 무엇을·왜 했는지 명확히
- [ ] `.env` 등 시크릿 파일이 커밋에 포함되지 않았는지 `git status`/`git diff --cached`로 확인 후 push

---

## 완료 후 Claude가 담당할 작업 (codex 작업 범위 아님)
- [ ] 구현 코드 리뷰 (`/code-review`)
- [ ] 실사용 검증 (Claude Code / Codex 양쪽에서 실제 tool 호출)
- [ ] `docs/setup.md` 사용법 문서 작성
