from mcp_server.config import Settings
from mcp_server.server import _create_mcp


def test_create_mcp_preserves_stdio_defaults() -> None:
    server = _create_mcp(Settings(require_api_key=False))

    assert server._token_verifier is None
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8000


def test_create_mcp_configures_authenticated_streamable_http() -> None:
    server = _create_mcp(
        Settings(
            require_api_key=False,
            mcp_transport="streamable-http",
            mcp_bearer_token="test-token",
        )
    )

    assert server._token_verifier is not None
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8765
    assert server.settings.auth is not None
    assert server.settings.transport_security is not None
    assert not server.settings.transport_security.enable_dns_rebinding_protection
