# ChatGPT에서 Cloudflare Quick Tunnel MCP 사용하기

이 문서는 로컬에서 실행되는 Deep Research MCP 서버를 Cloudflare Quick
Tunnel로 외부에 노출하고 ChatGPT에 연결할 때 필요한 절차와 인증 제약을
정리합니다.

> 결론부터 말하면, 현재 프로젝트의 `MCP_BEARER_TOKEN` 방식은 Codex
> CLI와 Claude Code에서는 사용할 수 있지만 ChatGPT의 인증된 MCP 연결
> 방식과는 호환되지 않습니다. FastMCP가 protected-resource metadata
> 일부를 자동 생성하지만, ChatGPT에서 인증을 사용하려면 완전한 OAuth
> 2.1 authorization server와 discovery를 구현해야 합니다. 따라서 Quick Tunnel은 현재 서버의 HTTP
> 전송과 인증 동작을 시험하는 용도로 사용하고, ChatGPT에 안전하게
> 상시 연결할 때는 OAuth 2.1과 고정 URL을 갖춘 named tunnel 또는
> OpenAI Secure MCP Tunnel을 권장합니다.

## 1. 구성과 지원 범위

```text
ChatGPT 또는 MCP 클라이언트
        │ HTTPS
        ▼
https://<random>.trycloudflare.com/mcp
        │ Cloudflare Quick Tunnel
        ▼
http://127.0.0.1:8765/mcp
        │
        ▼
Deep Research MCP ── SearXNG ── Redis
        │
        └── 설정한 LLM API
```

| 사용 경로 | 현재 프로젝트 상태 |
| --- | --- |
| 로컬 Codex/Claude의 stdio | 지원 |
| 원격 Codex/Claude + 정적 Bearer 토큰 | 지원 |
| ChatGPT + 인증 없음 | 서버가 의도적으로 거부하므로 미지원 |
| ChatGPT + 정적 Bearer 토큰 | ChatGPT가 요구하는 OAuth discovery가 없어 미지원 |
| ChatGPT + OAuth 2.1 | 서버와 별도의 authorization server 구현이 필요 |

ChatGPT는 로컬 stdio 서버에 직접 연결하지 않고 공개 HTTPS의
streamable HTTP MCP endpoint를 요구합니다. OpenAI의 현재 공식 인증
계약은 인증된 MCP 서버에 OAuth 2.1, protected-resource metadata,
authorization-server metadata, PKCE와 클라이언트 등록/식별 절차를
요구합니다.

- [OpenAI: MCP 서버 연결 및 테스트](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [OpenAI: MCP 사용자 인증](https://developers.openai.com/plugins/build/auth)
- [OpenAI: Developer mode와 MCP 앱](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta)

## 2. 사전 준비

먼저 로컬 MCP와 검색 백엔드가 정상인지 확인합니다.

```bash
cd /path/to/researcher
docker compose up -d
curl -fsS 'http://127.0.0.1:8080/search?q=test&format=json'
```

`cloudflared`를 설치한 뒤 버전을 확인합니다.

```bash
cloudflared --version
```

설치 방법은 운영체제별
[Cloudflare 공식 다운로드 문서](https://developers.cloudflare.com/tunnel/downloads/)를
따릅니다. Quick Tunnel은 Cloudflare 계정이나 소유 도메인이 없어도
사용할 수 있지만, 매번 임의의 `*.trycloudflare.com` 주소가 생성되는
개발·테스트 전용 기능입니다.

## 3. 인증된 원격 MCP 서버 실행

토큰을 셸 변수로 만들고 `.env`에 원격 설정을 추가합니다. 아래 명령은
토큰을 화면에 출력하므로 공유 화면이나 셸 기록을 주의하세요.

```bash
python3.12 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HOST=127.0.0.1
MCP_PORT=8765
MCP_BEARER_TOKEN=<생성한 토큰>
```

서버를 첫 번째 터미널에서 실행합니다.

```bash
.venv/bin/python mcp_server/server.py
```

서버는 `127.0.0.1`에서만 수신합니다. `MCP_TRANSPORT=streamable-http`인데
토큰이 없거나, `MCP_HOST`를 외부 인터페이스로 지정하면 기동을
거부합니다. 외부 노출은 항상 `cloudflared`가 담당합니다.

## 4. Quick Tunnel 열기

두 번째 터미널에서 저장소 스크립트를 실행합니다.

```bash
scripts/tunnel.sh
```

출력에서 다음 형태의 URL을 찾습니다.

```text
https://random-words.trycloudflare.com
```

편의를 위해 셸 변수로 저장합니다.

```bash
export TUNNEL_URL='https://random-words.trycloudflare.com'
```

Quick Tunnel을 재시작하면 URL이 바뀝니다. Cloudflare 공식 문서상
Quick Tunnel은 최대 200개의 동시 요청으로 제한되고 SSE를 지원하지
않습니다. 이 프로젝트는 streamable HTTP를 사용하지만, 개발용 터널에
SLA가 없고 URL이 바뀌므로 장시간 리서치나 상시 연결에는 named tunnel이
더 적합합니다.

- [Cloudflare: Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)

## 5. 터널과 Bearer 인증 검증

다음 요청에서 `<TOKEN>`은 `.env`의 `MCP_BEARER_TOKEN` 값으로
바꿉니다.

토큰이 없으면 `401 Unauthorized`여야 합니다.

```bash
curl -i "$TUNNEL_URL/mcp" \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

올바른 토큰을 보내면 `200 OK`와 MCP `initialize` 응답이 와야 합니다.

```bash
curl -i "$TUNNEL_URL/mcp" \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Authorization: Bearer <TOKEN>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

이 검증이 실패하면 ChatGPT 등록을 시도하지 말고 다음 순서로
확인합니다.

1. MCP 서버와 `cloudflared` 프로세스가 모두 실행 중인지 확인합니다.
2. `$TUNNEL_URL` 뒤에 `/mcp`를 붙였는지 확인합니다.
3. `.env`를 변경한 뒤 MCP 서버를 재시작했는지 확인합니다.
4. `~/.cloudflared/config.yaml`이 있으면 Quick Tunnel과 충돌할 수
   있으므로 Cloudflare 문서에 따라 잠시 이름을 변경합니다.

## 6. ChatGPT에 등록할 때의 현재 제약

ChatGPT의 UI 명칭은 배포 상태와 플랜에 따라 `Apps`, `Plugins`,
`Developer mode`, `Create` 등으로 다르게 보일 수 있습니다. 공식
절차의 공통 흐름은 다음과 같습니다.

1. ChatGPT 웹에서 Developer mode를 활성화합니다.
2. Settings의 Apps/Plugins에서 새 MCP 앱 또는 연결을 만듭니다.
3. MCP URL로 `$TUNNEL_URL/mcp`를 입력합니다.
4. ChatGPT가 도구와 인증 metadata를 스캔하도록 합니다.

하지만 현재 프로젝트는 모든 원격 요청에 정적 Bearer 토큰을 요구하고,
FastMCP가 `/.well-known/oauth-protected-resource/mcp`를 자동으로
제공하기는 합니다. 그러나 이 metadata는 로컬 `127.0.0.1` issuer를
가리키며 실제 authorization server, authorization endpoint, token
endpoint를 제공하지 않습니다. 따라서 ChatGPT의 도구 스캔은 완전한
OAuth 승인 흐름을 진행하지 못하고 실패하는 것이 정상입니다. 이 문서의
curl 성공은 “터널과 정적 토큰이
동작한다”는 뜻이지 “ChatGPT OAuth 연결이 완성됐다”는 뜻은 아닙니다.

공개 Quick Tunnel에서 인증을 제거하면 이론적으로 익명 연결이 가능하지만
누구나 LLM API 비용을 발생시키고 로컬 검색·출력 도구를 호출할 수
있으므로 이 프로젝트는 해당 모드를 제공하지 않습니다.

## 7. ChatGPT 인증을 완성하려면

ChatGPT에 인증된 MCP 앱으로 연결하려면 다음 작업이 추가로 필요합니다.

1. 고정 HTTPS 주소를 준비합니다. OAuth resource identifier와 metadata
   URL이 안정적이어야 하므로 주소가 매번 바뀌는 Quick Tunnel보다
   Cloudflare named tunnel과 소유 도메인이 적합합니다.
2. MCP resource server에 RFC 9728 protected-resource metadata를
   제공합니다. 현재 FastMCP가
   `/.well-known/oauth-protected-resource/mcp`를 자동 생성하지만,
   공개 resource URL과 실제 authorization server를 가리키도록
   구성해야 합니다.
3. authorization server가
   `/.well-known/oauth-authorization-server` 또는
   `/.well-known/openid-configuration`을 제공합니다.
4. Authorization Code + PKCE, `resource` parameter, access token 검증,
   그리고 ChatGPT가 지원하는 CIMD/DCR/사전 등록 클라이언트 방식 중
   하나를 구현합니다.
5. 장기 연결이 필요하면 `offline_access`와 refresh token 발급을
   지원합니다.
6. ChatGPT에서 URL을 다시 스캔하고 OAuth 승인 흐름을 완료합니다.

현재 `StaticTokenVerifier`는 하나의 공유 토큰만 비교하므로 위 OAuth
authorization server 역할을 하지 않습니다. 단순히 Cloudflare Access를
앞에 붙이는 것만으로 MCP OAuth discovery가 자동 구현되는 것도
아닙니다.

로컬 서버를 공개 인터넷에 노출하지 않는 것이 우선이라면 OpenAI가
제공하는 [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)도
검토할 수 있습니다. Cloudflare를 계속 사용하면서 상시 운영하려면
[Cloudflare named tunnel 설정](https://developers.cloudflare.com/tunnel/setup/)과
OAuth 2.1 구현을 함께 진행해야 합니다.

## 8. 보안 체크리스트

- `.env`와 `MCP_BEARER_TOKEN`을 Git에 커밋하지 않습니다.
- SearXNG와 MCP origin은 계속 `127.0.0.1`에만 바인딩합니다.
- 터널 URL과 토큰을 채팅, 이슈, 로그에 함께 남기지 않습니다.
- 토큰이 유출되면 새 토큰을 만들고 MCP 서버를 재시작합니다.
- Quick Tunnel 종료 후 공개 URL이 더 이상 응답하지 않는지 확인합니다.
- ChatGPT용 OAuth를 구현하기 전까지 정적 토큰을 OAuth처럼 취급하지
  않습니다.
- 개인 테스트를 넘어가면 Quick Tunnel 대신 고정 도메인, OAuth,
  사용자별 권한, 요청 제한과 감사 로그를 사용합니다.
