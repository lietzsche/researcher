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
