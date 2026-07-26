import pytest

from mcp_server.auth import StaticTokenVerifier


@pytest.mark.asyncio
async def test_static_token_verifier_accepts_matching_token() -> None:
    access_token = await StaticTokenVerifier("expected-token").verify_token(
        "expected-token"
    )

    assert access_token is not None
    assert access_token.token == "expected-token"


@pytest.mark.asyncio
async def test_static_token_verifier_rejects_wrong_token() -> None:
    access_token = await StaticTokenVerifier("expected-token").verify_token(
        "wrong-token"
    )

    assert access_token is None


@pytest.mark.asyncio
async def test_static_token_verifier_rejects_missing_token() -> None:
    access_token = await StaticTokenVerifier("expected-token").verify_token("")

    assert access_token is None
