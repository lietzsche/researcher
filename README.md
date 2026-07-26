# Deep Research MCP

주제의 목차를 먼저 설계하고 각 섹션을 GPT-Researcher와 로컬
SearXNG로 독립 리서치해, 재사용 가능한 섹션 파일과 하나의 학습 문서를
생성하는 로컬 stdio MCP 서버입니다.

## 설치 및 실행 개요

요구 사항은 Python 3.12, Docker Compose, DeepSeek API 키(기본) 또는
Anthropic/OpenAI API 키입니다.

```bash
python3.12 -m venv .venv   # Windows에서는 python(또는 py -3.12) -m venv .venv
.venv/bin/pip install -e '.[dev]'   # Windows: .venv\Scripts\pip install -e ".[dev]"
cp .env.example .env   # Windows: copy .env.example .env
# .env에 API 키와 임의의 SEARXNG_SECRET을 설정
docker compose up -d
curl 'http://localhost:8080/search?q=test&format=json'
```

Windows 공식 Python 설치본은 `python3`/`python3.12`가 아니라 `python`만 등록합니다 —
`python3`이 없다고 나오면 정상이니, `python --version`으로 3.12.x인지 확인 후
`python`(또는 여러 버전이 깔려있으면 `py -3.12`)으로 바꿔서 실행하세요. 자세한
Windows 설치 절차는 [docs/setup.md §2](./docs/setup.md#2-설치)를 참고하세요.

기본 모델은 `deepseek-v4-flash`(빠른 처리·본문 작성)와
`deepseek-v4-pro`(목차 설계)이며, 두 모델 모두 2026-07-26 실제 API
호출로 검증했습니다. Anthropic/OpenAI를 대신 사용할 때는
`.env.example`처럼 API 키뿐 아니라 세 LLM 모델 값도 해당 프로바이더로
함께 변경합니다.

`.env`는 Git에서 제외됩니다. SearXNG는 `127.0.0.1:8080`에만
바인딩되며 MCP 서버는 기본적으로 stdio transport만 사용합니다. Claude
Code/Codex CLI가 없는 환경이나 claude.ai 웹에서 붙이고 싶다면
[docs/setup.md §7](./docs/setup.md#7-원격-접속-선택-cloudflare-quick-tunnel)의
선택적 원격(streamable-http + 토큰 인증 + Cloudflare Quick Tunnel) 모드를
참고하세요.

## MCP 클라이언트 연결

저장소의 [`.mcp.json`](./.mcp.json)은 `${CLAUDE_PROJECT_DIR}/.venv/bin/python`을
직접 가리킵니다 — Claude Code가 자동으로 주입하는 `CLAUDE_PROJECT_DIR` 덕분에
clone 위치와 무관하게, macOS/Linux/WSL에서 `.venv`만 만들어 두면 별도 설정
없이 그대로 연결됩니다. CLI로 다른 인터프리터를 명시하려면 다음과 같이
실행할 수 있습니다.

```bash
claude mcp add --scope project deep-research -- \
  "$PWD/.venv/bin/python" "$PWD/mcp_server/server.py"
```

Windows에서는 command를 `.venv\Scripts\python.exe` 절대 경로로 바꿉니다.
Windows Claude Code에서 WSL의 서버를 실행할 때는 `wsl.exe -e` 뒤에 WSL
Python과 `server.py`의 절대 경로를 전달할 수 있습니다.

Codex CLI용 프로젝트 설정은 저장소의 [`.codex/config.toml`](./.codex/config.toml)에
포함되어 있습니다. WSL/Linux에서는 Git 저장소 루트를 실행 시점에 찾아
사용하므로 clone 위치가 달라도 설정을 수정할 필요가 없습니다. 프로젝트마다
`.venv`를 만든 뒤 저장소 안에서 `codex`를 실행합니다.

```toml
[mcp_servers.deep-research]
command = "bash"
args = [
  "-lc",
  'root="$(git rev-parse --show-toplevel)" && exec "$root/.venv/bin/python" "$root/mcp_server/server.py"',
]
```

Windows 네이티브 Codex CLI에서는 `.venv\Scripts\python.exe`를 사용하는
별도의 사용자 설정이 필요합니다. 이 저장소의 기본 Codex 설정은 WSL/Linux
환경을 대상으로 합니다.

서버를 직접 실행할 수도 있습니다.

```bash
.venv/bin/python mcp_server/server.py
```

노출되는 도구는 `generate_toc`, `research_section`,
`build_study_document`, `quick_search` 네 개입니다. 생성물은
`outputs/<topic-slug>/` 아래의 `toc.json`, `toc.md`, `manifest.json`,
`sections/*.md`, `study_document.md` 구조로 저장됩니다.
