# Deep Research MCP

주제의 목차를 먼저 설계하고 각 섹션을 GPT-Researcher와 로컬
SearXNG로 독립 리서치해, 재사용 가능한 섹션 파일과 하나의 학습 문서를
생성하는 로컬 stdio MCP 서버입니다.

## 설치 및 실행 개요

요구 사항은 Python 3.12, Docker Compose, DeepSeek API 키(기본) 또는
Anthropic/OpenAI API 키입니다.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
# .env에 API 키와 임의의 SEARXNG_SECRET을 설정
docker compose up -d
curl 'http://localhost:8080/search?q=test&format=json'
```

기본 모델은 `deepseek-v4-flash`(빠른 처리·본문 작성)와
`deepseek-v4-pro`(목차 설계)이며, 두 모델 모두 2026-07-26 실제 API
호출로 검증했습니다. Anthropic/OpenAI를 대신 사용할 때는
`.env.example`처럼 API 키뿐 아니라 세 LLM 모델 값도 해당 프로바이더로
함께 변경합니다.

`.env`는 Git에서 제외됩니다. SearXNG는 `127.0.0.1:8080`에만
바인딩되며 MCP 서버는 stdio transport만 사용합니다.

## MCP 클라이언트 연결

저장소의 [`.mcp.json`](./.mcp.json)은 `python`이 프로젝트 의존성이
설치된 환경을 가리킨다는 전제의 Claude Code 설정 예시입니다. CLI로
프로젝트의 Unix 계열 `.venv`를 명시하려면 다음과 같이 실행할 수 있습니다.

```bash
claude mcp add --scope project deep-research -- \
  "$PWD/.venv/bin/python" "$PWD/mcp_server/server.py"
```

Windows에서는 command를 `.venv\Scripts\python.exe` 절대 경로로 바꿉니다.
Windows Claude Code에서 WSL의 서버를 실행할 때는 `wsl.exe -e` 뒤에 WSL
Python과 `server.py`의 절대 경로를 전달할 수 있습니다.

Codex CLI의 `~/.codex/config.toml`에는 실제 저장소 절대 경로로 바꾼 다음
아래 스니펫을 추가합니다. 저장소 구현은 사용자 전역 config를 수정하지
않습니다.

```toml
[mcp_servers.deep-research]
command = "/absolute/path/to/researcher/.venv/bin/python"
args = ["/absolute/path/to/researcher/mcp_server/server.py"]
```

서버를 직접 실행할 수도 있습니다.

```bash
.venv/bin/python mcp_server/server.py
```

노출되는 도구는 `generate_toc`, `research_section`,
`build_study_document`, `quick_search` 네 개입니다. 생성물은
`outputs/<topic-slug>/` 아래의 `toc.json`, `toc.md`, `manifest.json`,
`sections/*.md`, `study_document.md` 구조로 저장됩니다.
