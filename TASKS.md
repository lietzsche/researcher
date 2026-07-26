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
- [x] `mcp_server/server.py`, `mcp_server/auth.py` 삭제
- [x] `.mcp.json` 삭제
- [x] `.codex/config.toml` 삭제, `.gitignore`에서 `.codex/*`/`!.codex/config.toml` 예외 규칙 제거
- [x] `docs/chatgpt-cloudflare-quick-tunnel.md` 삭제 (원격 MCP 모드가 없어지므로 — 사용자가 최근에 직접 작성한 문서지만 MCP 자체를 걷어내는 이번 전환 범위에 포함됨, 자세한 배경은 DESIGN.md §15 참고 박스)
- [x] `scripts/tunnel.sh` 삭제
- [x] `tests/test_auth.py`, `tests/test_server.py` 삭제
- [x] `pyproject.toml`에서 `mcp` 의존성 제거
- [x] `.env.example`에서 `MCP_TRANSPORT`/`MCP_HOST`/`MCP_PORT`/`MCP_BEARER_TOKEN`/`MCP_SERVER_NAME` 제거
- [x] README.md/docs/setup.md의 Claude Code/Codex/ChatGPT MCP 등록 안내 전체 제거 (README.md는 이후 Claude가 마무리하지만, 명백히 죽은 MCP 안내는 codex가 지워도 됨 — 헷갈리지 않게 "웹앱으로 전환됨, 자세한 사용법은 docs/setup.md 참고" 한 줄 정도로만 남겨둘 것)

### 12.1 디렉터리 이름 변경
- [x] `mcp_server/` → `app/`로 이름 변경, 패키지 내부 `from mcp_server....` import 전부 `from app....`로 갱신 (재사용 파일: `toc.py`, `research.py`, `assemble.py`, `storage.py`, `schemas.py`, `config.py`, 관련 테스트 전부)

### 12.2 config.py 정리
- [x] `mcp_transport`/`mcp_host`/`mcp_port`/`mcp_bearer_token`/`mcp_server_name` 필드와 관련 검증 로직 제거
- [x] `site_password: str | None` 필드 추가 (`SITE_PASSWORD` 환경변수에서 로드, 필수 아님 — 비어있으면 인증 없이 구동하되 시작 시 경고 로그)
- [x] `research_output_dir` 기본값을 컨테이너 환경에 맞게 조정 검토 (`.env.example`은 `/data/outputs` 같은 컨테이너 내부 경로 예시로)
- [x] DeepSeek/Anthropic/OpenAI/임베딩/gpt-researcher 버전 핀 관련 필드·검증은 전부 그대로 유지 (건드리지 말 것)

### 12.3 FastAPI 앱 (`app/main.py`, 신규)
- [x] DESIGN.md §7 표의 8개 라우트 구현: `POST /api/topics`, `GET /api/topics`, `GET /api/topics/{slug}`, `POST /api/topics/{slug}/sections/{section_id}/research`, `POST /api/topics/{slug}/build`, `GET /api/topics/{slug}/document`, `GET /api/topics/{slug}/download`, `DELETE /api/topics/{slug}`
- [x] `POST .../research`, `POST .../build`는 즉시 202를 반환하고 실제 작업은 `app/jobs.py`의 큐에 등록 (아래 12.4)
- [x] `GET /api/topics`는 `outputs/` 디렉터리를 스캔해서 각 주제의 manifest 요약(진행률, 생성일 등) 반환
- [x] `SITE_PASSWORD`가 설정돼 있으면 모든 `/api/*` 라우트와 정적 프론트엔드에 FastAPI `HTTPBasic` + `secrets.compare_digest`로 인증 적용 (DESIGN.md §12)
- [x] 정적 프론트엔드(`app/static/`)를 FastAPI `StaticFiles`로 서빙
- [x] 존재하지 않는 `slug` 요청 시 404, 진행 중인 섹션에 중복 리서치 요청 시 409 등 명확한 에러 응답

### 12.4 백그라운드 작업 큐 (`app/jobs.py`, 신규)
- [x] 프로세스 내 `asyncio` 기반 **직렬** 작업 큐 구현 (동시에 하나만 실행 — DESIGN.md §8 이유 참고: `_configure_gpt_researcher`의 `os.environ` 전역 변경이 병렬 실행 시 경쟁 상태를 만듦)
- [x] 큐에 쌓인/실행 중인 작업은 `manifest.json`의 섹션 상태(`pending`→`in_progress`→`done`/`error`)로 이미 표현되므로, 별도 작업 상태 저장소를 새로 만들지 말고 이 상태를 그대로 진행 상황 소스로 사용

### 12.5 프론트엔드 (`app/static/`, 신규)
- [x] 빌드 툴체인 없는 순수 HTML/CSS/바닐라 JS로 DESIGN.md §9의 4개 화면 구현: 홈(주제 목록+다운로드/삭제), 새 주제 생성, 목차 화면(전체 리서치 시작 버튼 + 섹션별 개별 리서치 버튼), 진행/상세 화면(폴링 기반 상태 갱신)
- [x] 반응형 CSS로 모바일 브라우저에서도 정상 동작 확인 (실제 폰 화면 크기로 최소 1회 확인 권장)

### 12.6 Docker Compose / 배포
- [x] `Dockerfile` 작성 (app 이미지: Python 3.12, `pip install -e .`, uvicorn으로 `app.main:app` 구동)
- [x] `docker-compose.yml`에 `app`(포트 미노출, `outputs/`를 호스트 디렉터리에 바인드 마운트), `cloudflared`(`command: tunnel --url http://app:8000`) 서비스 추가. 기존 `redis`/`searxng`는 유지하되 `SEARXNG_URL`을 컨테이너 네트워크 호스트명(`http://searxng:8080`)으로 조정
- [x] `scripts/up.sh`: `docker compose up -d` + 헬스체크 대기 + 아래 `get-tunnel-url.sh` 호출
- [x] `scripts/down.sh`: `docker compose down`
- [x] `scripts/get-tunnel-url.sh`: `docker compose logs cloudflared`에서 최신 `https://*.trycloudflare.com` URL 추출해 출력

### 12.7 테스트
- [x] `tests/test_api.py` (신규): FastAPI `TestClient`/`httpx.AsyncClient`로 각 라우트 스모크 테스트 (주제 생성, 목록 조회, 삭제, 인증 미들웨어 동작 — 실제 LLM 호출은 목이나 기존 테스트 패턴대로 팩토리 주입)
- [x] 기존 `test_toc.py`/`test_research.py`/`test_assemble.py`/`test_storage.py`는 import 경로만 `app.`으로 바꿔서 그대로 통과해야 함 (로직 변경 금지)

### 12.8 실사용 검증
- [x] 로컬(WSL 등)에서 `docker compose up -d`로 전체 스택(redis/searxng/app/cloudflared) 기동 확인
- [x] `scripts/get-tunnel-url.sh`로 뽑은 URL로 실제 브라우저 접속 → 주제 생성 → 목차 확인 → 섹션 1개 리서치 → 다운로드 → 삭제까지 전 과정 curl 또는 브라우저로 최소 1회 실행
- [x] `SITE_PASSWORD` 없이 접속 시 401(또는 정책에 맞는 거부)이 실제로 뜨는지 확인
- [x] 결과를 커밋 메시지에 남길 것

### 12.9 커밋 규율
- [x] 논리 단위로 커밋 분리 (예: 삭제/이름변경 → config 정리 → API → jobs → 프론트엔드 → Docker/배포 → 테스트), `.env`/비밀번호가 커밋에 안 들어가는지 확인 후 push

---

## Phase 13 — UI 개선 (DESIGN.md §17)

> Phase 12 완료 후 실사용(모바일 포함)에서 발견된 4건. 설계 명세는 DESIGN.md §17 참고. 아래 순서대로 구현.

### 13.1 [이 섹션만 리서치] 버튼 비활성화 (§17.1)
- [x] `app/static/app.js`: `renderToc()` 에서 manifest 로드 직후 `const isRunning = manifest.sections.some(s => s.status === "in_progress");` 설정
- [x] `tocSection(section, manifest, isRunning)` 시그니처에 `isRunning` 추가, `disabled` 조건을 `isRunning || state?.status === "in_progress" || state?.status === "done"` 으로 변경
- [x] `in_progress` 상태인 섹션의 버튼 텍스트를 "진행 중…" 으로 변경
- [x] `isRunning` 이면 [전체 리서치 시작] 버튼도 비활성화
- [x] `isRunning` 이면 TOC 화면도 3초 간격 폴링 시작, 화면 상단에 안내 문구 표시

### 13.2 단일 섹션 결과 열람 (§17.2)
- [x] `app/main.py`: `GET /api/topics/{slug}/sections/{section_id}` 엔드포인트 추가 — 섹션 파일 내용을 `text/markdown; charset=utf-8` 로 반환, 미완료이거나 파일이 없으면 404
- [x] `app/static/app.js`: `statusRow()` 에서 `done` 상태 섹션에 [보기] 버튼 추가 (`href="#/topic/{slug}/section/{section_id}"`)
- [x] `app/static/app.js`: `renderSectionDocument(slug, sectionId)` 함수 구현, `route()` 에 `#/topic/{slug}/section/{section_id}` 라우트 추가

### 13.3 다운로드 파일 인코딩 수정 (§17.3)
- [x] `app/main.py`: `download_document` 의 `media_type` 을 `"text/markdown; charset=utf-8"` 로 변경
- [x] `app/main.py`: `get_document` 의 `media_type` 도 `"text/markdown; charset=utf-8"` 로 변경
- [x] `app/main.py`: §13.2에서 추가하는 섹션 엔드포인트도 동일하게 charset 명시 (이미 위에서 명시)

### 13.4 마크다운 렌더링 (§17.4)
- [x] `app/static/index.html`: `<head>` 에 marked.js CDN 스크립트 태그 추가
- [x] `app/static/app.js`: `renderDocument(slug)` 함수 구현 (fetch → `marked.parse()` → HTML 표시, [다운로드] + [← 돌아가기] 제공)
- [x] `app/static/app.js`: `route()` 에 `#/topic/{slug}/document` 라우트 추가
- [x] `app/static/app.js`: progress 화면의 [전체 문서 보기] 링크를 새 해시 라우트로 변경
- [x] `app/static/style.css`: `.prose` 타이포그래피 스타일 추가 (헤딩, 목록, 코드, 링크, 수평선, 행간)
- [x] §13.2의 `renderSectionDocument` 도 `.prose` 스타일과 `marked.parse()` 사용
- [x] `tests/test_api.py`: §13.2에서 추가한 섹션 엔드포인트 테스트 추가 (done 섹션 → 200, pending/없음 → 404)

## Phase 14 — 전체 문서 보기 앵커 클릭 시 홈으로 튕기는 버그 수정 (DESIGN.md §17.5)

> Phase 13 완료 후 실사용 중 발견된 회귀. `app/static/app.js`만 변경, 백엔드/`assemble.py`는 건드리지 않는다.

- [x] `app/static/app.js`: `enableInPageAnchors(container)` 헬퍼 함수 추가 (DESIGN.md §17.5 코드 그대로) — 컨테이너에 클릭 이벤트 위임, `href="#..."` 링크 클릭 시 `document.getElementById`로 대상이 실제 존재하면 `preventDefault()` + `scrollIntoView({behavior:"smooth", block:"start"})`, 없으면 그대로 두어 기존 라우터가 처리하게 함
- [x] `renderDocument(slug)`: `.prose` 렌더링 직후 `enableInPageAnchors(appRoot.querySelector(".prose"))` 호출
- [x] `renderSectionDocument(slug, sectionId)`: 동일하게 `enableInPageAnchors` 호출 (현재 섹션 문서엔 내부 앵커가 없어 당장 버그는 아니지만 방어적으로 동일 처리)
- [x] 기존 라우트 링크(`← 돌아가기`, `목차와 작업 선택`, `다운로드` 등)는 영향받지 않는지 확인 — 이 링크들은 `href="#/topic/..."` 형태라 `document.getElementById`가 대응하는 엘리먼트를 못 찾으므로 자동으로 기존 라우터 흐름을 타야 함
- [x] 실제로 주제 하나를 끝까지 빌드해서(또는 이미 완료된 주제가 있으면 재사용) [전체 문서 보기] 화면에서 목차의 섹션 링크를 클릭 → 홈으로 안 튕기고 해당 섹션으로 스크롤되는지 브라우저(또는 헤드리스 브라우저)로 직접 확인
- [x] 위 확인과 별개로 [← 돌아가기]/[목차와 작업 선택]/[다운로드] 링크가 여전히 정상 동작하는지도 같이 확인
- [x] 결과를 커밋 메시지에 남기고 push

## Phase 15 — 최종 결과물 언어 강제 (DESIGN.md §18)

> Phase 14 완료 후 실사용 중 발견된 이슈. **범위 정정**: 검색(리서치) 과정을 한글로 강제하는 게 아니라, 리서치가 끝난 뒤 나오는 섹션 본문(결과물)만 한글로 나오면 된다 — 검색어/SearXNG 언어 필터/`_research_query()`는 이번 범위에서 건드리지 않는다. 원인 조사는 DESIGN.md §18에 이미 끝나 있음 — `LANGUAGE` 환경변수 설정은 효과 없다는 것도 확인됐으니 그 방향으로 고치지 말 것.

- [x] `app/config.py`: `Settings`에 `output_language: str = "Korean"`(env `OUTPUT_LANGUAGE`) 필드 하나만 추가, `load_settings()`에서 env 로딩
- [x] `app/research.py`: `research_section()`의 `write_report(custom_prompt=...)` 문자열에 다음 한 줄만 추가 (DESIGN.md §18.2 그대로):
  ```python
  f"Write your entire response in {settings.output_language}, "
  "regardless of the language of the source material."
  ```
- [x] `_research_query()`(서브쿼리/검색 프롬프트), `quick_search()`, `searxng/settings.yml`, `toc.py`는 **건드리지 않는다** — 이번 Phase의 핵심 결정이니 임의로 확장하지 말 것
- [x] `tests/test_research.py`: `research_section()`이 구성하는 `custom_prompt`(fake researcher factory가 캡처한 값)에 `settings.output_language` 값이 포함되는지 테스트 추가
- [x] config 기본값 테스트: `output_language == "Korean"`
- [x] 실제로 `research_section`을 한글 주제로 1회 실행해 섹션 본문 서술이 한글로 나오는지 확인 (출처 URL/제목은 원문 언어 그대로가 정상이니 그건 확인 대상 아님). 결과를 커밋 메시지에 남길 것
- [x] TASKS.md 맨 아래 "완료 후 Claude가 담당할 작업" 항목은 네 범위가 아니니 건드리지 마
- [x] 논리 단위로 커밋 나눠서 push까지

## Phase 16 — 섹션 파일 조회를 title 재계산 대신 manifest의 path로 통일 (DESIGN.md §19)

> 실사용 중 발견된 이슈: 섹션이 `done`인데 파일을 못 찾아 404가 남 (제목이 재계산 시점에 파일 생성 시점과 달라져 있었음, 정확한 원인은 로그 없이 미확정). 원인이 뭐든 재발을 막는 구조적 수정이 DESIGN.md §19에 있음 — title로 파일명을 재계산하는 대신 `manifest.json`에 이미 저장된 `path` 필드를 쓰도록 세 곳을 고친다.

- [x] `app/research.py`: `research_section()`의 `section_path = storage.section_path(section_id, section["title"])`(142번 줄)를 `section_path = storage.topic_dir / manifest_section["path"]`로 변경 (DESIGN.md §19.1)
- [x] `app/main.py`: `get_section_document`의 `section_path = storage.section_path(section_id, str(section.get("title", "")))`(296번 줄)를 `section_path = storage.topic_dir / str(section.get("path", ""))`로 변경 (DESIGN.md §19.2)
- [x] `app/assemble.py`: `assemble_study_document()`의 `section_path = storage.section_path(section_id, section["title"])`(64번 줄)를 이미 조회해둔 `state`(= `manifest_sections[section_id]`)의 `path`를 이용해 `section_path = storage.topic_dir / state["path"]`로 변경, `state`에 `path`가 없는 경우엔 기존 미완료/에러 표시 로직 유지 (DESIGN.md §19.3)
- [x] `storage.section_path()`/`section_filename()` 자체는 삭제하지 말 것 — `initialize_manifest()`가 최초 1회 계산할 때 여전히 필요함 (DESIGN.md §19.4)
- [x] `tests/test_research.py`/`test_assemble.py`/`test_api.py`에 회귀 테스트 추가: manifest의 `title`을 일부러 실제 파일명과 다르게 설정해둔 상황(이번에 실사용 중 겪은 상황 재현)에서도 `research_section`의 캐시 조회, `get_section_document`, `assemble_study_document`가 `path` 필드 기준으로 파일을 정상적으로 찾는지 확인 (DESIGN.md §19.5)
- [x] 위 회귀 테스트를 통해 "title이 파일 생성 후 바뀌어도 조회는 깨지지 않는다"는 게 실제로 확인되는지 최종 점검
- [x] TASKS.md 맨 아래 "완료 후 Claude가 담당할 작업" 항목은 네 범위가 아니니 건드리지 마
- [x] 논리 단위로 커밋 나눠서 push까지

## Phase 17 — 실사용 중 발견된 5건 (DESIGN.md §20)

> 실사용 중 보고된 다섯 가지: (1) "전체 리서치 시작" 후 홈으로 와도 무한로딩, (2) 서버 로그 페이지 필요, (3) 섹션 상세에서 바로 다음/이전 섹션 이동, (4) 다운로드 시 엑셀 옵션, (5) 섹션 리서치 병렬화. 각 항목의 원인 분석과 설계 근거는 DESIGN.md §20.1~§20.5에 상세히 있으니 반드시 먼저 읽을 것 — 특히 §20.1은 코드로 확인한 사실과 "가장 유력한 추정"을 구분해서 적어뒀다.

### 17.1 무한로딩 원인 대응 (DESIGN.md §20.1)
- [x] `app/research.py`: `_configure_gpt_researcher()` 안에서 `gpt_researcher.retrievers.searx.searx` 모듈의 `requests.get`을 `functools.partial`로 `timeout=settings.request_timeout_seconds`가 기본 적용되도록 몽키패치. 모듈 전역 플래그로 idempotent하게 가드(여러 번 호출돼도 중복 패치 안 되게).
- [x] `app/config.py`: `Settings`에 `section_timeout_seconds: float = 900`(env `SECTION_TIMEOUT_SECONDS`, 1~3600 검증) 추가.
- [x] `app/jobs.py`: `_research_one()`의 `research_section(...)` 호출을 `asyncio.wait_for(..., timeout=settings.section_timeout_seconds)`로 감싸기. 타임아웃 시 `storage.update_section(section_id, status="error")` 후 계속 진행(큐 전체를 막지 않음).
- [x] `app/static/app.js`: 공용 `api()` 헬퍼에 `AbortController` 기반 타임아웃(20초) 추가, 타임아웃 시 명확한 에러 토스트 표시.
- [x] 회귀 테스트: SearXNG 몽키패치가 `requests.get`에 타임아웃을 실제로 주입하는지, 반복 호출해도 한 번만 패치되는지 확인. `asyncio.wait_for` 타임아웃 시 섹션이 `error`로 남고 나머지 큐 처리가 계속되는지 확인(fake researcher factory로 인위적 지연 재현).
- [x] `.env.example`에 `SECTION_TIMEOUT_SECONDS` 추가.

### 17.2 서버 로그 페이지 (DESIGN.md §20.2)
- [x] `app/logs.py` 신규: `InMemoryLogHandler(logging.Handler)`가 `collections.deque(maxlen=1000)`에 `{id, timestamp, level, logger, message}` 저장, `id`는 단조 증가.
- [x] `create_app()`의 lifespan에서 루트 로거에 이 핸들러 부착.
- [x] `GET /api/logs?after_id=0&limit=200` 엔드포인트 추가 — `after_id`보다 큰 로그만 오름차순 반환. 인증은 기존 미들웨어가 전체 라우트에 이미 적용되니 별도 처리 불필요.
- [x] `app/static/app.js`: `#/logs` 라우트 추가, 홈 히어로에 "서버 로그" 링크 추가. 3~5초 폴링, 레벨별 색상 표시(error/warning 강조).
- [x] 테스트: 로그 핸들러가 로그를 쌓는지, `/api/logs?after_id=`가 커서 이후 것만 반환하는지, `maxlen` 초과 시 오래된 것부터 버려지는지.

### 17.3 섹션 상세 → 바로 다음/이전 섹션 (DESIGN.md §20.3)
- [x] `app/static/app.js`의 `renderSectionDocument(slug, sectionId)` 수정: 섹션 본문 fetch와 별도로 `GET /api/topics/{slug}`를 호출해 `toc` 순서 + `manifest.sections` 상태를 얻는다. 현재 섹션 인덱스를 찾아 이전/다음 section id 계산, 이웃 섹션이 `status === "done"`일 때만 링크 활성화.
- [x] 페이지에 "← 이전 섹션 / 다음 섹션 →" 버튼 추가(기존 "← 돌아가기"는 유지).
- [x] 백엔드 변경 없음 — 새 API 만들지 말 것 (기존 두 엔드포인트로 충분).

### 17.4 다운로드 엑셀 옵션 (DESIGN.md §20.4)
- [x] `pyproject.toml`에 `openpyxl` 의존성 추가.
- [x] `app/export.py` 신규: `build_excel_workbook(topic, storage) -> BytesIO` — 시트 "목차"(id/제목/설명), "본문"(id/제목/본문 텍스트, wrap), "출처"(id/제목/URL, 기존 `_SOURCE_LINK` 정규식과 동일 패턴으로 섹션 파일에서 추출).
- [x] `app/main.py`의 `download_document`에 `format: Literal["markdown", "excel"] = "markdown"` 쿼리 파라미터 추가(기본값 유지, 하위 호환). `excel`이면 워크북을 BytesIO로 만들어 올바른 Content-Type/filename으로 응답.
- [x] `app/static/app.js`: 다운로드 링크가 있는 세 곳(홈 카드, 진행 화면, 문서 화면) 모두 "다운로드 (MD)"/"다운로드 (Excel)" 두 링크로 분리.
- [x] 테스트: `format=excel` 응답이 유효한 xlsx인지(openpyxl로 다시 읽어 시트/셀 값 검증), `format` 생략/`markdown` 시 기존 동작 그대로인지.

### 17.5 섹션 리서치 병렬화 (DESIGN.md §20.5)
- [x] `app/config.py`에 `max_concurrent_research: int = 2`(env `MAX_CONCURRENT_RESEARCH`, 1~5 검증) 추가.
- [x] `app/jobs.py`의 `_run_build()`를 순차 `for` 루프 대신 `asyncio.Semaphore(settings.max_concurrent_research)`로 동시 실행 수를 제한한 `asyncio.gather(..., return_exceptions=True)`로 변경. 하나가 실패해도 나머지는 계속 진행(취소하지 않음).
- [x] 조립 조건 변경: 모든 섹션이 끝난 뒤 매니페스트를 다시 읽어 대상 섹션 전부가 `done`일 때만 `assemble_study_document` 호출, 하나라도 `error`면 조립 건너뛰고 로그에 남김.
- [x] 개별 "이 섹션만 리서치" 트리거는 건드리지 말 것 — 이번 병렬화는 build 전용.
- [x] 회귀 테스트: 여러 섹션을 동시에(가짜 지연이 있는 fake researcher factory로) 빌드했을 때 매니페스트 상태가 서로 덮어쓰지 않고 전부 정확히 반영되는지, 동시 실행 수가 `max_concurrent_research`를 넘지 않는지(세마포어로 카운팅), 일부 실패 시 조립이 스킵되는지, 전부 성공 시 조립되는지.
- [x] `.env.example`에 `MAX_CONCURRENT_RESEARCH` 추가.

### 공통
- [x] `docs/setup.md`에 새 환경변수(`SECTION_TIMEOUT_SECONDS`, `MAX_CONCURRENT_RESEARCH`), 로그 페이지 사용법, 엑셀 다운로드 옵션, 섹션 상세 다음/이전 이동 안내 추가.
- [x] TASKS.md 맨 아래 "완료 후 Claude가 담당할 작업" 항목은 네 범위가 아니니 건드리지 마.
- [x] 논리 단위로 커밋 나눠서 push까지.

## Phase 18 — 병렬 빌드 기본값을 직렬로 되돌리고 검색 실패를 눈에 띄게 (DESIGN.md §21)

> Phase 17 배포 직후 실사용 테스트에서 6개 섹션 중 2개가 완전히 빈 컨텍스트로 실패하고, 나머지도 서브쿼리 대부분에서 검색 결과를 못 찾은 채 LLM이 할루시네이션으로 채운 정황이 발견됨. 가장 유력한 원인은 병렬 빌드(§20.5)가 자체 호스팅 SearXNG에 거는 동시 부하 — DESIGN.md §21에 근거와 한계를 상세히 적어뒀으니 반드시 먼저 읽을 것. **완전히 확진된 원인은 아니라는 점, 그리고 이번 수정이 §20.5의 병렬 메커니즘 자체를 없애는 게 아니라 기본값만 안전하게 되돌리는 것이라는 점**을 정확히 이해하고 시작해.

- [x] `app/config.py`: `max_concurrent_research`의 `Field(default=2, ...)` → `Field(default=1, ...)`. `load_settings()`의 `os.getenv("MAX_CONCURRENT_RESEARCH", "2")` → `os.getenv("MAX_CONCURRENT_RESEARCH", "1")`. 검증 범위(1~5)와 세마포어/`asyncio.gather` 메커니즘 자체는 절대 건드리지 말 것.
- [x] `.env.example`, `docker-compose.yml`의 `MAX_CONCURRENT_RESEARCH` 기본값도 1로 통일.
- [x] `app/jobs.py`: 섹션 리서치 결과의 `sources`가 비어 있으면(`len(sources) == 0`) `logger.warning(...)`으로 섹션 id/토픽/상태를 남긴다 (섹션 상태는 여전히 `done` 그대로 — 상태를 `error`로 바꾸지 말 것, 진단 가시성만 추가하는 것임). `_research_one()`이 `research_section()`의 반환값을 받는 지점에 추가하는 게 자연스러움.
- [x] `docs/setup.md`: §2의 `MAX_CONCURRENT_RESEARCH` 기본값 문구를 1로 정정하고 "값을 올리면 자체 호스팅 SearXNG가 동시 요청에 레이트리밋/차단될 수 있다"는 경고 추가. §6 "검색 실패 시 조용히 빈 섹션" 항목에 "이제 서버 로그에 `source_count == 0` 경고가 남는다" 한 줄 추가.
- [x] 테스트:
  - `app/config.py` 기본값이 1인지 확인하는 테스트 추가/수정.
  - `sources`가 빈 섹션이 `done` 상태를 유지하면서 WARNING 로그를 남기는지 확인하는 회귀 테스트(fake researcher factory + `caplog`).
  - 기존 §20.5 병렬 테스트들(`Settings(..., max_concurrent_research=2)`처럼 명시적으로 값을 지정한 것들)은 기본값 변경과 무관하게 그대로 통과해야 함 — 혹시 기본값에 암묵적으로 의존하는 테스트가 있다면 명시적으로 고칠 것.
- [x] TASKS.md 맨 아래 "완료 후 Claude가 담당할 작업" 항목은 네 범위가 아니니 건드리지 마.
- [x] 논리 단위로 커밋 나눠서 push까지.

---

## 완료 후 Claude가 담당할 작업 (codex 작업 범위 아님)
- [x] 구현 코드 리뷰 — 발견한 4건(전부 심각도 높음)을 직접 수정: `gpt-researcher` 0.16.0 import 버그 → 버전 상한 고정, DeepSeek-only 설정에서 임베딩 때문에 죽는 문제 → `EMBEDDING` 기본값 추가, `RETRIEVER` 환경변수 충돌로 2섹션 이상 `build_study_document`가 항상 실패하던 버그 → 수정, 한글 주제가 해시 폴더명으로 뭉개지던 `slugify` 버그 → 수정. 낮은 우선순위 2건(SearXNG 빈 검색 결과 조용히 통과, `SEARXNG_SECRET` 무효)은 DESIGN.md/docs/setup.md에 기록만 하고 미수정.
- [x] 실사용 검증: `generate_toc` → `research_section`(2섹션) → `assemble_study_document`를 실제 DeepSeek + 로컬 SearXNG로 끝까지 실행 ("베이즈 정리", "피보나치 수열"), 섹션당 10~18개 실제 출처 인용 확인. 위 버그들은 전부 이 과정에서 발견됨.
- [x] `docs/setup.md` 사용법 문서 작성
- [x] Phase 11 완료 후: 코드 리뷰 완료 (설계대로 구현됨, 추가 버그 없음). 로컬 stdio 모드 회귀 없음 확인 (`.env`에 원격 변수 미설정 시 `mcp_transport="stdio"`, `token_verifier=None` 그대로). streamable-http 서버를 직접 띄워 `curl`로 무인증/오답 토큰(401), 정답 토큰(200), 터널 Host 헤더를 흉내낸 요청(200)까지 독립적으로 재검증 완료. claude.ai 웹 커스텀 커넥터는 브라우저 UI 라이브 검증까지는 못함 — docs/setup.md 7.3에 미검증임을 명시. `docs/setup.md`에 "7. 원격 접속 (선택)" 섹션 작성, README.md의 stdio-only 문구도 갱신.
- [x] Phase 12 완료 후: 코드 리뷰 — `POST /sections/{id}/research`가 이미 `done`인 섹션도 `force` 없이 그대로 재큐잉하던 버그 발견·수정 (build 엔드포인트는 이미 done 섹션을 걸러내는데 단일 섹션 엔드포인트만 그 보호가 빠져있었음; 프론트엔드가 완료된 섹션 버튼을 비활성화해서 일반 사용 흐름에선 안 걸리지만 API를 직접 호출하면 불필요한 재과금이 발생할 수 있었음 — 회귀 테스트 추가). `docker compose up -d --build`로 전체 스택(redis/searxng/app/cloudflared) 실기동 확인 후 실제 Quick Tunnel URL로 무인증(401)/오답 비밀번호(401)/정상 비밀번호(200) 확인, 이어서 실제 DeepSeek 호출로 주제 생성("소크라테스의 산파술")→섹션 리서치(중복 요청 409, 완료 후 재요청 409, force=true 허용 확인)→전체 빌드→다운로드(한글 파일명 인코딩 정상)→삭제→404 확인까지 curl로 전 과정 실행. `docs/setup.md`를 웹앱 배포/사용법 기준으로 재작성, README.md도 웹앱 퀵스타트로 갱신.
- [x] Phase 14 완료 후: 코드 리뷰 — 설계(§17.5) 그대로 정확히 구현됨, 추가 문제 없음. codex가 실제 Chrome 헤드리스로 전체 문서/섹션 문서 양쪽 앵커 스크롤(0→649px, →2356px)과 ← 돌아가기/목차와 작업 선택/다운로드 링크 회귀 없음까지 검증 완료. 테스트 20개 재실행으로 재확인.
- [x] Phase 15 완료 후: 코드 리뷰 — 설계(§18) 그대로 정확히 구현됨, 범위 이탈 없음 (`_research_query()`/`quick_search()`/`searxng/settings.yml`/`toc.py` 전부 diff 없음으로 직접 확인). codex가 실제 한글 주제("광합성")로 `research_section` 실행해 한글 3,859자 대 라틴 1,270자(75.2% 한글)까지 정량 검증 완료. 테스트 23개 재실행으로 재확인.
- [x] Phase 16 완료 후: 코드 리뷰 — 설계(§19) 그대로 정확히 구현됨, `assemble.py`는 `path` 필드 자체가 없는 레거시 manifest 케이스까지 방어적으로 처리하는 걸 추가로 확인(설계에 없던 좋은 보강). 세 지점(research_section 캐시/get_section_document/assemble_study_document) 모두 title-drift 재현 테스트로 커버됨을 직접 diff로 확인. 테스트 27개 재실행으로 재확인.
- [x] Phase 17 완료 후: 코드 리뷰 — 설계(§20) 대체로 정확히 구현됨. 직접 수정한 문제 2건:
  - `app/research.py`의 SearXNG 타임아웃 몽키패치가 `searx_module.requests.get`을 직접 덮어써서, `searx.py`가 참조하는 `requests` 모듈 객체가 프로세스 전체가 공유하는 바로 그 `requests` 패키지와 동일 객체라 **의도와 달리 전역 `requests.get`을 패치**하고 있었음(설계는 "SearXNG 리트리버 경계에서만" 보정한다고 명시했었음). `searx_module.requests` 자체를 새 프록시 객체로 교체하는 방식으로 좁혀 SearxSearch만 영향받도록 수정, 전역 `requests.get`이 그대로인지 확인하는 회귀 테스트 추가.
  - `app/export.py`의 엑셀 본문 시트가 섹션 본문을 셀 길이 제한 없이 그대로 넣고 있어서, Excel의 셀당 32,767자 한도를 넘는 섹션(이 앱의 핵심 기능인 "deep" 심화 리서치 챕터는 출처 포함 시 쉽게 이 한도를 넘김)의 내용이 openpyxl에 의해 **경고 없이 조용히 잘려나가는** 문제를 발견 — 직접 재현해 확인함(40,000자 입력 → 저장 후 32,767자로 잘림). 한도 초과 시 잘렸다는 안내 문구를 붙이고 Markdown 다운로드를 참고하라고 표시하도록 수정, 회귀 테스트 추가(`tests/test_export.py`).
  - 나머지(17.2 로그 뷰어, 17.3 섹션 이동, 17.5 병렬 빌드)는 설계·회귀 테스트 모두 정확함, 추가 수정 없음. 테스트 41개(신규 3개 포함) 재실행으로 재확인.
  - 실사용 검증 한계: 이 환경엔 실제 DeepSeek API 접근이 없어 Phase 10/12/15처럼 실제 리서치 호출로 끝까지 검증하지는 못함 — 로직/회귀 테스트/Node 기반 프론트엔드 테스트로만 확인했다. 무한로딩(§20.1)의 근본 원인도 여전히 "가장 유력한 추정"일 뿐 확진은 아니므로, 재발 시 새 로그 페이지(§20.2)로 어느 단계에서 멈췄는지 먼저 확인할 것.
- [ ] (향후, 별도 설계) 오디오 오버뷰 파이프라인 설계
