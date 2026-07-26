# 사용법 (Setup & Usage)

로컬 stdio MCP 서버로 학습 문서를 생성하는 방법입니다. 아키텍처와 설계 근거는 [DESIGN.md](../DESIGN.md)를 참고하세요.

## 1. 요구 사항

- Python 3.12
- Docker / Docker Compose (SearXNG + Redis 구동용)
- LLM API 키 하나: **DeepSeek(기본, 비용 이유)**, 또는 Anthropic, 또는 OpenAI

## 2. 설치

```bash
git clone <this-repo>
cd researcher
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

`.env`를 열어 다음을 채웁니다.

- `DEEPSEEK_API_KEY` (기본 프로바이더). Anthropic/OpenAI로 바꾸려면 `.env.example`의 대체 옵션 블록을 참고해 키와 `FAST_LLM`/`SMART_LLM`/`STRATEGIC_LLM` 세 값을 함께 바꾸세요.
- `SEARXNG_SECRET`은 임의의 문자열로 채워도 되지만, 현재 이미지는 이 값을 실제로 사용하지 않습니다 (아래 "알려진 이슈" 참고) — 로컬 전용 인스턴스라 보안상 문제는 없습니다.

## 3. SearXNG 기동

```bash
docker compose up -d
curl 'http://localhost:8080/search?q=test&format=json'
```

JSON 응답이 오면 정상입니다. `127.0.0.1:8080`에만 바인딩되어 외부에 노출되지 않습니다.

## 4. 클라이언트에 MCP 서버 등록

### Claude Code CLI

```bash
claude mcp add --scope project deep-research -- \
  "$PWD/.venv/bin/python" "$PWD/mcp_server/server.py"
```

프로젝트에 이미 포함된 [`.mcp.json`](../.mcp.json)을 대신 사용해도 되지만, `python`이 이 프로젝트의 의존성이 설치된 인터프리터를 가리키는 경우에만 동작합니다 — 확실하지 않다면 위 `claude mcp add` 명령으로 `.venv`의 절대 경로를 직접 지정하세요.

### Codex CLI

`~/.codex/config.toml`에 추가 (절대 경로로 교체):

```toml
[mcp_servers.deep-research]
command = "/absolute/path/to/researcher/.venv/bin/python"
args = ["/absolute/path/to/researcher/mcp_server/server.py"]
```

## 5. 도구 사용법

네 가지 도구가 노출됩니다. 실제 사용 흐름은 보통 1 → (검토) → 3 순서입니다.

### ① `generate_toc` — 먼저 목차만 뽑기

```
generate_toc(topic="양자역학 입문", depth="standard")
```

- `depth`: `standard`(기본 6섹션) 또는 `deep`(기본 10섹션)
- `num_sections`: 섹션 수를 직접 지정하고 싶을 때
- 결과가 `outputs/<topic-slug>/toc.json`, `toc.md`에 저장됩니다. **본문 리서치는 아직 하지 않습니다** — 이 단계에서 `toc.md`를 열어 목차가 마음에 드는지 검토하세요. 마음에 안 들면 `force_regenerate`로 다시 뽑거나 직접 `toc.json`을 수정한 뒤 다음 단계로 넘어가면 됩니다.

### ② `research_section` — 섹션 하나만 심화 리서치

```
research_section(topic="양자역학 입문", section_id="03")
```

- 목차 중 특정 섹션만 다시 파고들고 싶을 때 사용 (전체를 재실행할 필요 없음).
- 이미 완료된(`done`) 섹션은 기본적으로 재실행하지 않고 캐시된 결과를 반환합니다. 강제로 다시 하려면 `force=true`.

### ③ `build_study_document` — 전체 파이프라인 한 번에

```
build_study_document(topic="양자역학 입문", depth="standard")
```

- TOC가 없으면 자동으로 먼저 생성합니다.
- 아직 완료되지 않은 섹션들을 순서대로 리서치한 뒤, 최종적으로 `outputs/<topic-slug>/study_document.md`로 조립합니다.
- 섹션이 많으면 수 분~수십 분 걸릴 수 있습니다. 진행 상황은 MCP progress notification으로 전달됩니다 ("N/총 섹션 완료: <제목>").
- `sections_filter=["03","05"]`로 특정 섹션들만 대상으로 돌릴 수 있고, `force_regenerate=true`면 전체를 처음부터 다시 만듭니다.

### ④ `quick_search` — 가벼운 단발 검색

```
quick_search(query="용어 뜻", num_results=5)
```

- 리서치 파이프라인을 거치지 않고 SearXNG에 바로 질의합니다. 공부하다 용어 하나 빠르게 확인할 때 용도.

## 6. 결과물 구조

```
outputs/<topic-slug>/
  manifest.json       # 섹션별 상태(pending/in_progress/done/error), 소스 개수
  toc.md / toc.json    # 목차
  sections/*.md        # 섹션별 심화 리서치 결과 + 출처
  study_document.md     # 전체를 이어붙인 최종 학습 문서
```

`manifest.json`의 섹션 상태를 보면 어디까지 완료됐는지 알 수 있습니다. 이 구조는 향후 오디오 오버뷰 단계가 섹션 파일을 그대로 소비할 수 있도록 의도적으로 섹션 단위 파일로 유지됩니다.

## 7. 알려진 이슈 / 주의사항

- **`gpt-researcher` 버전 고정 필요**: 최신 배포판인 0.16.0에는 `gpt_researcher/actions/query_processing.py`에 `typing` import 순서 버그가 있어(`Any`/`List`를 함수 시그니처에서 사용한 뒤에야 `from typing import ...`가 실행됨), 이 버전이 설치되면 `research_section`/`build_study_document`가 `import gpt_researcher` 시점에 `NameError`로 즉시 실패합니다. `generate_toc`/`quick_search`는 `gpt_researcher`를 import하지 않아 영향받지 않습니다. `pyproject.toml`에 `gpt-researcher>=0.14.0,<0.16.0`로 상한을 고정해 이 회귀를 피하도록 해뒀습니다 — 업스트림에서 수정되기 전까지는 이 핀을 유지하세요.
- **`SEARXNG_SECRET`은 현재 아무 효과가 없습니다**: `docker-compose.yml`이 이 환경변수를 컨테이너에 전달하지만, SearXNG 이미지의 엔트리포인트 스크립트는 이 변수를 전혀 읽지 않습니다. 실제 `secret_key`는 `searxng/settings.yml`에 하드코딩된 `"change-me-before-use"` 값 그대로 사용됩니다. 이 인스턴스는 `127.0.0.1`에만 바인딩되고 외부에 노출되지 않으므로 보안 위험은 아니지만, `.env`에서 값을 바꿔도 반영되지 않는다는 점은 알아두세요.
- **검색 실패 시 조용히 빈 섹션이 만들어질 수 있음**: SearXNG가 모든 쿼리에 대해 빈 결과를 반환하면(차단/레이트리밋 등), GPT-Researcher는 오류를 던지는 대신 "소스를 찾지 못했다"는 안내 문구를 리포트 본문으로 반환합니다. 현재 `research_section`은 이 경우도 정상 `done` 상태로 저장합니다 — 결과물 품질이 이상하다면 해당 섹션의 `manifest.json`에서 `source_count`가 0인지 확인하세요.
