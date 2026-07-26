# 사용법 (Setup & Usage)

개인 우분투 서버에 Docker Compose로 띄우고 Cloudflare Quick Tunnel로 접속하는 개인용 학습 리서치 웹앱입니다. 아키텍처와 설계 근거는 [DESIGN.md](../DESIGN.md)를 참고하세요.

## 1. 요구 사항

- Docker / Docker Compose
- LLM API 키 하나: **DeepSeek(기본, 비용 이유)**, 또는 Anthropic, 또는 OpenAI
- (원격 접속용) `cloudflared` — 별도 설치 불필요, `docker-compose.yml`의 `cloudflared` 서비스가 컨테이너로 함께 뜸

## 2. 설치 및 기동

```bash
git clone <this-repo>
cd researcher
cp .env.example .env
```

`.env`를 열어 다음을 채웁니다.

- `DEEPSEEK_API_KEY` (기본 프로바이더). Anthropic/OpenAI로 바꾸려면 `.env.example`의 대체 옵션 블록을 참고해 키와 `FAST_LLM`/`SMART_LLM`/`STRATEGIC_LLM` 세 값을 함께 바꾸세요.
- `TOC_TIMEOUT_SECONDS`는 목차 생성 LLM 호출의 최대 대기 시간(기본 180초, 허용 범위 1~1200초), `SECTION_TIMEOUT_SECONDS`는 섹션 하나의 최대 리서치 시간(기본 900초), `MAX_CONCURRENT_RESEARCH`는 전체 빌드 안에서 동시에 실행할 섹션 수(기본 1, 허용 범위 1~5)입니다. 자체 호스팅 SearXNG에서는 동시 실행 값을 올리면 짧은 시간에 검색 요청이 몰려 외부 검색엔진의 레이트리밋이나 차단으로 빈 결과가 늘어날 수 있으므로 기본값을 권장합니다.
- **`SITE_PASSWORD`**: 반드시 강력한 값으로 채우세요. 비워두면 앱이 인증 없이 뜨고 시작 로그에 경고를 남깁니다 — Quick Tunnel로 공개되는 순간 누구나 접근/삭제/DeepSeek 예산 소비가 가능해집니다. 생성 예시:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(24))"
  ```
- `SEARXNG_SECRET`은 임의의 문자열로 채워도 되지만, 현재 SearXNG 이미지는 이 값을 실제로 사용하지 않습니다 (§6 "알려진 이슈" 참고) — 컨테이너 내부 네트워크에만 존재해 보안상 문제는 없습니다.

전체 스택(Redis, SearXNG, 앱, Cloudflare Quick Tunnel)을 한 번에 띄웁니다.

```bash
scripts/up.sh
```

서비스가 모두 healthy해질 때까지 기다린 뒤, 현재 세션의 Quick Tunnel URL(`https://<임의문자열>.trycloudflare.com`)을 출력합니다. 이 URL이 앱 접속 주소입니다 — 브라우저(PC/모바일 아무거나)로 열면 `SITE_PASSWORD`를 요구하는 기본 인증 팝업이 뜹니다 (사용자명은 아무거나 무시되고, 비밀번호만 검증됩니다. 실제로는 `researcher`를 사용자명으로 둡니다).

```bash
scripts/down.sh
```

로 전체 스택을 내립니다. 이후 다시 `scripts/up.sh`를 실행하면 **Quick Tunnel URL이 바뀝니다** — 매번 새로 확인해야 합니다. URL만 다시 확인하고 싶으면:

```bash
scripts/get-tunnel-url.sh
```

앱 코드를 수정한 뒤 재배포만 하고 싶다면(터널은 그대로 유지):

```bash
scripts/redeploy.sh
```

`app` 이미지만 다시 빌드하고 `app` 컨테이너만 재생성합니다. `redis`/`searxng`/`cloudflared`는 건드리지 않으므로 **Quick Tunnel URL이 바뀌지 않습니다**. `Dockerfile`이 의존성 설치(torch 포함) 레이어를 애플리케이션 코드 복사보다 앞에 두고 있어서, 코드만 바뀐 경우엔 이 무거운 설치 단계가 캐시로 재사용되고 몇 초 내에 끝납니다.

### SearXNG가 차단당할 때 유료 리트리버로 폴백하기 (선택)

서버 로그 페이지에 `source_count=0`인 검색 실패 경고가 반복된다면, SearXNG 시도가 예외를 내거나 출처를 하나도 찾지 못했을 때 유료 검색 API로 한 번 더 자동 재시도하도록 설정할 수 있습니다.

지원하는 리트리버 이름과 서비스 페이지는 다음과 같습니다.

- `tavily`: [Tavily](https://www.tavily.com/)
- `serper`: [Serper](https://serper.dev/)
- `serpapi`: [SerpApi](https://serpapi.com/)
- `searchapi`: [SearchApi](https://www.searchapi.io/)
- `exa`: [Exa](https://exa.ai/)

(Bing은 지원하지 않습니다 — Microsoft가 [2025년 8월 11일 기존 인스턴스까지 포함해 Bing Search API를 완전히 폐지](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)했고, 후속 서비스인 "Grounding with Bing Search"는 호환되지 않는 별개의 API라 이미 발급받은 키가 있어도 쓸 수 없습니다.)

각 서비스의 무료 크레딧과 가격은 수시로 바뀌므로 위 가입 페이지의 최신 가격 정책을 직접 확인하세요.

이 프로젝트는 기본적으로 관리할 비밀과 과금 대상이 DeepSeek API 키 하나뿐이지만, 이 옵션은 그 원칙의 명시적인 선택적 예외입니다. 활성화하면 두 번째 유료 API 키를 관리해야 합니다. 유료 리트리버는 SearXNG가 계속 실패할 때만 호출되므로 정상적인 검색 중에는 추가 과금이 없지만, 대량 차단 상황에서는 여러 섹션이 폴백을 사용해 비용이 빠르게 늘 수 있습니다.

선택한 서비스에서 키를 발급받은 뒤 `.env`에 다음 두 값을 추가하고 앱을 재배포합니다.

```dotenv
FALLBACK_RETRIEVER=tavily
FALLBACK_RETRIEVER_API_KEY=<발급받은 키>
```

## 3. 웹 UI 사용법

1. **홈**: 저장된 주제 카드 목록. 진행률(N/M 섹션), 생성일이 보이고, 완료된 주제는 Markdown/Excel/섹션별 ZIP 다운로드 버튼이 나타납니다. 목차 생성 중이거나 실패한 주제는 진행률 대신 상태 배지가 표시됩니다. "삭제"는 언제든 가능(목차 생성 또는 리서치 진행 중인 주제 제외). 히어로의 **서버 로그**에서 최근 1,000개 로그를 확인할 수 있고, 화면은 4초마다 새 로그를 가져옵니다. SearXNG 검색이 예외 또는 빈 출처로 실패하면 응답 없는 엔진의 오류를 바탕으로 봇 차단 가능성을 판정한 WARNING 로그도 여기에 남습니다. GPT-Researcher가 실제 검색에는 LLM이 만든 여러 하위 쿼리를 사용하므로, 이 진단은 실패한 하위 쿼리를 정확히 재현한 결과가 아니라 같은 SearXNG 인스턴스와 시점에서 원본 섹션 쿼리로 확인한 근사치입니다.
2. **새 주제 만들기**: 주제 텍스트와 깊이(standard=6섹션/deep=10섹션)를 입력하고 제출하면 서버가 즉시 202를 반환하고 목차 생성을 백그라운드 큐에서 시작합니다. 생성 화면은 3초마다 상태를 자동 갱신하며, 완료 뒤에 본문 리서치를 선택할 수 있습니다.
3. **목차 화면**: 생성된 목차를 검토합니다. 여기서 두 가지를 고를 수 있습니다.
   - "**전체 리서치 시작**" — 남은 섹션을 `MAX_CONCURRENT_RESEARCH` 한도 안에서 병렬 리서치하고, 대상 섹션이 모두 완료되면 최종 문서를 조립합니다.
   - 섹션별 "**이 섹션만 리서치**" — 원하는 섹션만 골라 진행합니다. 이미 완료된 섹션은 버튼이 비활성화됩니다.
4. **진행 화면**: 섹션별 상태(대기/진행 중/완료/오류)와 출처 개수를 보여주고, 몇 초 간격으로 자동 갱신됩니다. "전체 리서치 시작"을 누르면 POST 완료를 기다리지 않고 즉시 이 화면으로 이동합니다. 브라우저 탭을 닫아도 서버는 계속 진행하니, 나중에 다시 열어 확인하면 됩니다. 완료된 섹션 상세에서는 본문 **위와 아래**의 이전 섹션/다음 섹션 버튼으로 바로 이동할 수 있으며, 이웃 섹션이 미완료이면 버튼이 비활성화됩니다. 전체 문서가 조립되면 "전체 문서 보기"/Markdown·Excel/섹션별 ZIP 다운로드 버튼이 나타납니다.

## 4. REST API

웹 UI 없이 직접 호출할 수도 있습니다 (모두 `SITE_PASSWORD`가 설정돼 있으면 HTTP Basic Auth 필요, 사용자명 `researcher` + 비밀번호).

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/topics` | `{topic, depth, num_sections?}` → 202 `{slug, status: "queued"}`. 목차는 백그라운드 생성 (본문 리서치는 시작 안 함) |
| `GET` | `/api/logs?after_id=0&limit=200` | 서버 로그를 ID 커서 이후부터 조회 |
| `GET` | `/api/topics` | 저장된 주제 목록 요약 |
| `GET` | `/api/topics/{slug}` | 목차 + 섹션별 상태 상세 |
| `POST` | `/api/topics/{slug}/sections/{section_id}/research?force=false` | 섹션 하나 리서치 시작 (202, 백그라운드). 이미 완료된 섹션은 `force=true` 없이는 409로 거부됩니다. |
| `POST` | `/api/topics/{slug}/build` | `{sections_filter?, force_regenerate?}` → 미완료 섹션 전체 리서치 + 조립 (202, 백그라운드) |
| `GET` | `/api/topics/{slug}/document` | 조립된 문서 본문 (markdown) |
| `GET` | `/api/topics/{slug}/download?format=markdown\|excel\|zip` | 조립된 문서를 Markdown(기본), Excel 또는 TOC 순서의 완료 섹션별 ZIP으로 다운로드 |
| `DELETE` | `/api/topics/{slug}` | 주제 전체 삭제 (리서치 진행 중이면 409) |

목차 생성과 리서치 트리거(`POST /api/topics`, `.../research`, `.../build`)는 즉시 202를 반환합니다. 서버의 바깥 작업 큐는 직렬이므로 개별 요청끼리는 순서대로 처리되지만, 전체 빌드 하나가 실행되는 동안에는 그 빌드의 섹션들이 `MAX_CONCURRENT_RESEARCH` 한도만큼 병렬 실행됩니다.

## 5. 결과물 구조

```
outputs/<topic-slug>/
  manifest.json       # 섹션별 상태(pending/in_progress/done/error), 소스 개수 — API의 진행 상황 소스
  toc.md / toc.json    # 목차
  sections/*.md        # 섹션별 심화 리서치 결과 + 출처
  study_document.md     # 전체를 이어붙인 최종 학습 문서
```

`docker-compose.yml`이 `outputs/`를 호스트 디렉터리에 바인드 마운트하므로, `docker compose down` 후 다시 올려도 데이터가 남습니다. 완전히 지우려면 웹 UI/API의 삭제 기능을 쓰거나 `outputs/<slug>/` 디렉터리를 직접 지우세요.

## 6. 알려진 이슈 / 주의사항

- **`gpt-researcher` 버전 고정 필요**: 최신 배포판인 0.16.0에는 `gpt_researcher/actions/query_processing.py`에 `typing` import 순서 버그가 있어(`Any`/`List`를 함수 시그니처에서 사용한 뒤에야 `from typing import ...`가 실행됨), 이 버전이 설치되면 리서치 관련 기능이 `import gpt_researcher` 시점에 `NameError`로 즉시 실패합니다. `pyproject.toml`에 `gpt-researcher>=0.14.0,<0.16.0`로 상한을 고정해 이 회귀를 피하도록 해뒀습니다 — 업스트림에서 수정되기 전까지는 이 핀을 유지하세요.
- **`SEARXNG_SECRET`은 현재 아무 효과가 없습니다**: `docker-compose.yml`이 이 환경변수를 컨테이너에 전달하지만, SearXNG 이미지의 엔트리포인트 스크립트는 이 변수를 전혀 읽지 않습니다. 실제 `secret_key`는 `searxng/settings.yml`에 하드코딩된 값 그대로 사용됩니다. SearXNG는 컨테이너 네트워크 안에서만 존재하고 호스트/외부에 노출되지 않으므로 보안 위험은 아닙니다.
- **검색 실패 시 섹션이 `error`로 남고 자동 재시도 대상이 됩니다**: SearXNG가 모든 쿼리에 대해 빈 결과를 반환하면(차단/레이트리밋 등), GPT-Researcher는 오류를 던지는 대신 소스를 찾지 못했다는 안내 문구(또는 근거 없는 서술)를 리포트 본문으로 반환합니다. 실제 출처를 하나도 못 찾은 경우(`source_count == 0`) 이 섹션은 `done`이 아니라 `error`로 기록되고, 서버 로그에 WARNING이 남습니다 — 목차 화면에서 "이 섹션만 리서치" 버튼이 그대로 활성화되어 있으니 바로 재시도하면 됩니다. 다음 "전체 리서치 시작"에서도 자동으로 다시 시도됩니다. (이 동작이 적용되기 전, 이미 `done`으로 저장된 레거시 섹션이 있다면 UI 버튼이 비활성화돼 있으니 `POST /api/topics/{slug}/sections/{id}/research?force=true`를 직접 호출해 재시도하세요.)
- **Quick Tunnel은 상시 서비스가 아닙니다**: Cloudflare의 무료/베스트에포트 기능이라 SLA가 없고, URL이 재시작마다 바뀝니다. 서버(정확히는 `cloudflared` 컨테이너)가 켜져 있는 동안만 접속됩니다.
- **서버 재시작 후 작업 상태 복구**: 앱 시작 시 이전 프로세스가 남긴 `in_progress` 섹션은 `pending`으로 되돌려 다시 실행하거나 삭제할 수 있게 합니다. 중단된 목차 생성은 `error`로 바뀌며, 오류 화면에서 주제를 삭제한 뒤 다시 만들 수 있습니다. 중단된 작업 자체를 자동 재실행하지는 않습니다.
- **섹션 시간 제한**: 개별 섹션이 `SECTION_TIMEOUT_SECONDS`를 넘기면 `error`로 기록하고 큐의 다른 작업은 계속합니다. 전체 빌드에서 하나라도 실패하면 다른 대상 섹션은 끝까지 진행하지만 최종 문서 조립은 생략됩니다. 서버 로그에서 실패 원인을 확인하세요.

## 7. 로컬 개발 (Docker 없이)

앱 코드만 빠르게 반복 작업하고 싶다면:

```bash
python3.12 -m venv .venv   # Windows: python 또는 py -3.12
.venv/bin/pip install -e '.[dev]'
docker compose up -d redis searxng   # SearXNG/Redis만 컨테이너로
SEARXNG_URL=http://localhost:8080 .venv/bin/uvicorn app.main:app --reload
```

이 경로에서는 `RESEARCH_OUTPUT_DIR`이 기본값(`./outputs`, 저장소 루트 기준)을 쓰므로 `.env`의 `/data/outputs` 값을 로컬 개발 시에는 오버라이드해야 할 수 있습니다.
