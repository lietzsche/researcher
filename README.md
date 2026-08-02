# Deep Research

주제를 넣으면 목차를 먼저 설계하고, 각 섹션을 GPT-Researcher와 로컬
SearXNG로 독립 리서치해 하나의 학습 문서로 조립하는 개인용 웹앱입니다.
Docker Compose로 우분투 서버 등에 띄우고 Cloudflare Quick Tunnel로 어디서든
(모바일 포함) 접속합니다.

```bash
git clone <this-repo>
cd researcher
cp .env.example .env
# .env에 DEEPSEEK_API_KEY와 SITE_PASSWORD를 채운 뒤
scripts/up.sh
```

출력된 `https://*.trycloudflare.com` URL을 브라우저로 열면 됩니다. 자세한
설정, API, 알려진 이슈는 [docs/setup.md](./docs/setup.md)를,
아키텍처/설계 근거는 [DESIGN.md](./DESIGN.md)를 참고하세요.

## 관심 주제 지속 리서치

상단의 **관심 주제** 메뉴에서 검색 주제를 등록하면 기존 `quick_search` 흐름으로
최신 결과를 스냅샷으로 저장하고 이전 실행과 비교합니다. 상세 화면에서 즉시
새로고침하거나 5분~7일 간격을 설정할 수 있으며, 결과는 출처 링크가 포함된
**추가 / 변경 / 제거 / 변경 없음**으로 표시됩니다. 사용법과 실패 재시도,
재시작 동작은 관심 주제 화면의 **사용 가이드**에서 바로 확인할 수 있습니다.

관심 주제 상태와 최근·이전 스냅샷은 `RESEARCH_OUTPUT_DIR/.watchlist/` 아래에
원자적으로 저장됩니다. 예약 실행은 단일 앱 프로세스가 살아 있는 동안 동작하는
best-effort 방식이며, 서버 중단 중 놓친 실행을 소급 수행하지 않습니다. 실제
결과 품질과 성공 여부는 실행 중인 SearXNG 및 선택한 API 제공자 접근 상태에
따라 달라집니다.
