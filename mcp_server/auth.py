"""Static bearer-token authentication for optional remote MCP access."""

from __future__ import annotations

import secrets

from mcp.server.auth.provider import AccessToken, TokenVerifier


class StaticTokenVerifier(TokenVerifier):
    """Verify one shared bearer token using a constant-time comparison."""

    def __init__(self, expected_token: str) -> None:
        if not expected_token:
            raise ValueError("expected_token must not be empty")
        self._expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or not secrets.compare_digest(token, self._expected_token):
            return None
        return AccessToken(
            token=token,
            client_id="deep-research-static-token",
            scopes=[],
        )
