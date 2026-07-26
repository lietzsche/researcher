# 구현 작업 체크리스트

> 설계 근거는 [DESIGN.md](./DESIGN.md) 참고. 목표는 학습용 문서 생성기: 주제 → 목차 → 섹션별 심화 리서치 → 조립된 학습 문서. codex가 아래 순서대로 구현.

> **2026-07-26 전환**: Phase 0-11(아래)은 MCP 서버로 구현했던 기록이고 전부 완료됐다. 이제 MCP를 걷어내고 개인 웹앱(FastAPI + Docker Compose + Cloudflare Quick Tunnel)으로 바꾼다 — **Phase 12**가 지금 할 일이다. Phase 0-11 중 `toc.py`/`research.py`/`assemble.py`/`storage.py`/`schemas.py`/`config.py`의 핵심 로직과 DeepSeek/임베딩/gpt-researcher 버전 핀 설정은 그대로 재사용하고, MCP 관련 부분(Phase 6, 7, 11)만 대체된다. 자세한 것은 DESIGN.md §15 "MCP → 웹앱 전환" 참고.

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

## Phase 11 — 원격 접속 옵션 (DESIGN.md 14장, Cloudflare Quick Tunnel)

> Phase 0-10은 완료됨. 이 phase는 로컬 stdio 기본 동작은 그대로 두고, 명시적으로 켰을 때만 동작하는 원격(streamable-http) 모드를 추가하는 선택 기능이다. 로컬 전용 사용자에게는 아무 영향이 없어야 한다 (`MCP_TRANSPORT` 미설정 시 지금과 100% 동일하게 동작).

- [x] `mcp_server/config.py`: `Settings`에 `mcp_transport`(기본 `"stdio"`), `mcp_host`(기본 `"127.0.0.1"`), `mcp_port`(기본 `8765`), `mcp_bearer_token`(`str | None`) 필드 추가. 검증 로직에 "`mcp_transport != 'stdio'`인데 `mcp_bearer_token`이 없으면 에러" 추가.
- [x] `mcp_server/auth.py` (신규): FastMCP `TokenVerifier` 프로토콜 구현체 — `Authorization: Bearer <token>`을 `secrets.compare_digest`로 상수 시간 비교. 잘못된/누락된 토큰은 인증 실패 처리.
- [x] `mcp_server/server.py`: `mcp_transport == "streamable-http"`일 때만 `FastMCP(...)`에 `host`/`port`/`token_verifier`를 전달하고, `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)`로 명시적으로 완화 (DESIGN.md 14.3의 Host-header 함정 때문 — 이유를 코드 주석에 남길 것). `main()`은 `mcp.run(transport=settings.mcp_transport)`로 분기.
- [x] `.env.example`: `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_BEARER_TOKEN`을 주석 처리된 선택 옵션으로 추가, 토큰 생성 명령어(`python -c "import secrets; print(secrets.token_urlsafe(32))"`) 예시 포함.
- [x] `scripts/tunnel.sh` (신규, 실행권한 부여): `cloudflared` 설치 여부 확인 후 `cloudflared tunnel --url http://$MCP_HOST:$MCP_PORT` 실행하는 래퍼. 미설치 시 설치 안내 메시지 출력.
- [x] `tests/`: 토큰 검증 유닛 테스트(정상 토큰/틀린 토큰/토큰 없음), config 검증 테스트(`mcp_transport=streamable-http`인데 `mcp_bearer_token` 없으면 에러).
- [x] `claude mcp add --help`로 원격 http transport 등록 문법 확인: `claude mcp add --transport http deep-research-remote "$TUNNEL_URL/mcp" --header "Authorization: Bearer $MCP_BEARER_TOKEN"` (Claude Code 2.1.214).
- [x] Codex CLI 0.141.0은 URL 기반 원격 MCP transport 지원 확인: `codex mcp add deep-research-remote --url "$TUNNEL_URL/mcp" --bearer-token-env-var MCP_BEARER_TOKEN`; TOML은 `url` + `bearer_token_env_var` 키 사용.
- [x] 실제 `MCP_TRANSPORT=streamable-http` 서버 + cloudflared 2026.5.2 Quick Tunnel에서 curl 검증: 무인증 `401`, 올바른 토큰의 MCP `initialize` 요청 `200` (2026-07-26).
- [x] Phase 9와 동일한 커밋 규율: 논리 단위로 커밋 분리, `.env`/토큰 값이 커밋에 안 들어가는지 확인 후 push.

## Phase 12 — MCP 제거, 개인 웹앱으로 전환 (DESIGN.md 전체 재작성분, 특히 §5, §7-13, §15)

> Phase 0-11은 완료된 과거 기록이며 그대로 두고 참고만 한다. 이 Phase가 지금 구현 대상이다.

### 12.0 삭제 (DESIGN.md §15 그대로)
- [ ] `mcp_server/server.py`, `mcp_server/auth.py` 삭제
- [ ] `.mcp.json` 삭제
- [ ] `scripts/tunnel.sh` 삭제
- [ ] `tests/test_auth.py`, `tests/test_server.py` 삭제
- [ ] `pyproject.toml`에서 `mcp` 의존성 제거
- [ ] `.env.example`에서 `MCP_TRANSPORT`/`MCP_HOST`/`MCP_PORT`/`MCP_BEARER_TOKEN`/`MCP_SERVER_NAME` 제거
- [ ] README.md/docs/setup.md의 Claude Code/Codex MCP 등록 안내 전체 제거 (README.md는 이후 Claude가 마무리하지만, 명백히 죽은 MCP 안내는 codex가 지워도 됨 — 헷갈리지 않게 "웹앱으로 전환됨, 자세한 사용법은 docs/setup.md 참고" 한 줄 정도로만 남겨둘 것)

### 12.1 디렉터리 이름 변경
- [ ] `mcp_server/` → `app/`로 이름 변경, 패키지 내부 `from mcp_server....` import 전부 `from app....`로 갱신 (재사용 파일: `toc.py`, `research.py`, `assemble.py`, `storage.py`, `schemas.py`, `config.py`, 관련 테스트 전부)

### 12.2 config.py 정리
- [ ] `mcp_transport`/`mcp_host`/`mcp_port`/`mcp_bearer_token`/`mcp_server_name` 필드와 관련 검증 로직 제거
- [ ] `site_password: str | None` 필드 추가 (`SITE_PASSWORD` 환경변수에서 로드, 필수 아님 — 비어있으면 인증 없이 구동하되 시작 시 경고 로그)
- [ ] `research_output_dir` 기본값을 컨테이너 환경에 맞게 조정 검토 (`.env.example`은 `/data/outputs` 같은 컨테이너 내부 경로 예시로)
- [ ] DeepSeek/Anthropic/OpenAI/임베딩/gpt-researcher 버전 핀 관련 필드·검증은 전부 그대로 유지 (건드리지 말 것)

### 12.3 FastAPI 앱 (`app/main.py`, 신규)
- [ ] DESIGN.md §7 표의 8개 라우트 구현: `POST /api/topics`, `GET /api/topics`, `GET /api/topics/{slug}`, `POST /api/topics/{slug}/sections/{section_id}/research`, `POST /api/topics/{slug}/build`, `GET /api/topics/{slug}/document`, `GET /api/topics/{slug}/download`, `DELETE /api/topics/{slug}`
- [ ] `POST .../research`, `POST .../build`는 즉시 202를 반환하고 실제 작업은 `app/jobs.py`의 큐에 등록 (아래 12.4)
- [ ] `GET /api/topics`는 `outputs/` 디렉터리를 스캔해서 각 주제의 manifest 요약(진행률, 생성일 등) 반환
- [ ] `SITE_PASSWORD`가 설정돼 있으면 모든 `/api/*` 라우트와 정적 프론트엔드에 FastAPI `HTTPBasic` + `secrets.compare_digest`로 인증 적용 (DESIGN.md §12)
- [ ] 정적 프론트엔드(`app/static/`)를 FastAPI `StaticFiles`로 서빙
- [ ] 존재하지 않는 `slug` 요청 시 404, 진행 중인 섹션에 중복 리서치 요청 시 409 등 명확한 에러 응답

### 12.4 백그라운드 작업 큐 (`app/jobs.py`, 신규)
- [ ] 프로세스 내 `asyncio` 기반 **직렬** 작업 큐 구현 (동시에 하나만 실행 — DESIGN.md §8 이유 참고: `_configure_gpt_researcher`의 `os.environ` 전역 변경이 병렬 실행 시 경쟁 상태를 만듦)
- [ ] 큐에 쌓인/실행 중인 작업은 `manifest.json`의 섹션 상태(`pending`→`in_progress`→`done`/`error`)로 이미 표현되므로, 별도 작업 상태 저장소를 새로 만들지 말고 이 상태를 그대로 진행 상황 소스로 사용

### 12.5 프론트엔드 (`app/static/`, 신규)
- [ ] 빌드 툴체인 없는 순수 HTML/CSS/바닐라 JS로 DESIGN.md §9의 4개 화면 구현: 홈(주제 목록+다운로드/삭제), 새 주제 생성, 목차 화면(전체 리서치 시작 버튼 + 섹션별 개별 리서치 버튼), 진행/상세 화면(폴링 기반 상태 갱신)
- [ ] 반응형 CSS로 모바일 브라우저에서도 정상 동작 확인 (실제 폰 화면 크기로 최소 1회 확인 권장)

### 12.6 Docker Compose / 배포
- [ ] `Dockerfile` 작성 (app 이미지: Python 3.12, `pip install -e .`, uvicorn으로 `app.main:app` 구동)
- [ ] `docker-compose.yml`에 `app`(포트 미노출, `outputs/`를 호스트 디렉터리에 바인드 마운트), `cloudflared`(`command: tunnel --url http://app:8000`) 서비스 추가. 기존 `redis`/`searxng`는 유지하되 `SEARXNG_URL`을 컨테이너 네트워크 호스트명(`http://searxng:8080`)으로 조정
- [ ] `scripts/up.sh`: `docker compose up -d` + 헬스체크 대기 + 아래 `get-tunnel-url.sh` 호출
- [ ] `scripts/down.sh`: `docker compose down`
- [ ] `scripts/get-tunnel-url.sh`: `docker compose logs cloudflared`에서 최신 `https://*.trycloudflare.com` URL 추출해 출력

### 12.7 테스트
- [ ] `tests/test_api.py` (신규): FastAPI `TestClient`/`httpx.AsyncClient`로 각 라우트 스모크 테스트 (주제 생성, 목록 조회, 삭제, 인증 미들웨어 동작 — 실제 LLM 호출은 목이나 기존 테스트 패턴대로 팩토리 주입)
- [ ] 기존 `test_toc.py`/`test_research.py`/`test_assemble.py`/`test_storage.py`는 import 경로만 `app.`으로 바꿔서 그대로 통과해야 함 (로직 변경 금지)

### 12.8 실사용 검증
- [ ] 로컬(WSL 등)에서 `docker compose up -d`로 전체 스택(redis/searxng/app/cloudflared) 기동 확인
- [ ] `scripts/get-tunnel-url.sh`로 뽑은 URL로 실제 브라우저 접속 → 주제 생성 → 목차 확인 → 섹션 1개 리서치 → 다운로드 → 삭제까지 전 과정 curl 또는 브라우저로 최소 1회 실행
- [ ] `SITE_PASSWORD` 없이 접속 시 401(또는 정책에 맞는 거부)이 실제로 뜨는지 확인
- [ ] 결과를 커밋 메시지에 남길 것

### 12.9 커밋 규율
- [ ] 논리 단위로 커밋 분리 (예: 삭제/이름변경 → config 정리 → API → jobs → 프론트엔드 → Docker/배포 → 테스트), `.env`/비밀번호가 커밋에 안 들어가는지 확인 후 push

---

## 완료 후 Claude가 담당할 작업 (codex 작업 범위 아님)
- [x] 구현 코드 리뷰 — 발견한 4건(전부 심각도 높음)을 직접 수정: `gpt-researcher` 0.16.0 import 버그 → 버전 상한 고정, DeepSeek-only 설정에서 임베딩 때문에 죽는 문제 → `EMBEDDING` 기본값 추가, `RETRIEVER` 환경변수 충돌로 2섹션 이상 `build_study_document`가 항상 실패하던 버그 → 수정, 한글 주제가 해시 폴더명으로 뭉개지던 `slugify` 버그 → 수정. 낮은 우선순위 2건(SearXNG 빈 검색 결과 조용히 통과, `SEARXNG_SECRET` 무효)은 DESIGN.md/docs/setup.md에 기록만 하고 미수정.
- [x] 실사용 검증: `generate_toc` → `research_section`(2섹션) → `assemble_study_document`를 실제 DeepSeek + 로컬 SearXNG로 끝까지 실행 ("베이즈 정리", "피보나치 수열"), 섹션당 10~18개 실제 출처 인용 확인. 위 버그들은 전부 이 과정에서 발견됨.
- [x] `docs/setup.md` 사용법 문서 작성
- [x] Phase 11 완료 후: 코드 리뷰 완료 (설계대로 구현됨, 추가 버그 없음). 로컬 stdio 모드 회귀 없음 확인 (`.env`에 원격 변수 미설정 시 `mcp_transport="stdio"`, `token_verifier=None` 그대로). streamable-http 서버를 직접 띄워 `curl`로 무인증/오답 토큰(401), 정답 토큰(200), 터널 Host 헤더를 흉내낸 요청(200)까지 독립적으로 재검증 완료. claude.ai 웹 커스텀 커넥터는 브라우저 UI 라이브 검증까지는 못함 — docs/setup.md 7.3에 미검증임을 명시. `docs/setup.md`에 "7. 원격 접속 (선택)" 섹션 작성, README.md의 stdio-only 문구도 갱신.
- [ ] Phase 12 완료 후: 코드 리뷰, Docker Compose로 전체 스택 실제 기동 검증, Quick Tunnel URL로 모바일 브라우저 접속 검증, `docs/setup.md`를 웹앱 배포/사용법 기준으로 재작성 (MCP 관련 내용 제거)
- [ ] (향후, 별도 설계) 오디오 오버뷰 파이프라인 설계
