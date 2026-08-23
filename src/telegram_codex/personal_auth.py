from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from .config import ConfigurationError

_DEFAULT_SCOPE = "telegram:personal"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required for remote MCP authentication")
    return value


def _scopes_from_env() -> list[str]:
    raw = os.getenv("TELEGRAM_MCP_OAUTH_SCOPES", _DEFAULT_SCOPE)
    scopes = [item.strip() for item in raw.replace(",", " ").split() if item.strip()]
    if not scopes:
        raise ConfigurationError("TELEGRAM_MCP_OAUTH_SCOPES must contain at least one scope")
    return scopes


def _scope_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item for item in value.split() if item]
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []


class StaticTokenVerifier(TokenVerifier):
    """Private-development verifier.

    This mode protects `/mcp` with one high-entropy bearer token. It is useful
    for curl/MCP Inspector and private tunnel smoke tests, but it is not the
    ChatGPT production authentication path because there is no OAuth login or
    refresh-token flow for ChatGPT to perform.
    """

    def __init__(self, token: str, scopes: list[str]) -> None:
        if len(token) < 32:
            raise ConfigurationError("TELEGRAM_MCP_STATIC_TOKEN must be at least 32 characters")
        self._digest = hashlib.sha256(token.encode("utf-8")).digest()
        self._scopes = list(scopes)

    async def verify_token(self, token: str) -> AccessToken | None:
        supplied = hashlib.sha256(token.encode("utf-8")).digest()
        if not secrets.compare_digest(self._digest, supplied):
            return None
        return AccessToken(
            token=token,
            client_id="telegram-personal-static",
            subject="personal-owner",
            scopes=self._scopes,
            claims={"iss": "telegram-personal-static"},
        )


class IntrospectionTokenVerifier(TokenVerifier):
    """RFC 7662 verifier for an external OAuth/OIDC authorization server."""

    def __init__(
        self,
        *,
        introspection_url: str,
        client_id: str,
        client_secret: str,
        issuer_url: str,
        resource_url: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._introspection_url = introspection_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._issuer_url = issuer_url.rstrip("/")
        self._resource_url = resource_url
        self._timeout = timeout_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._introspection_url,
                    data={"token": token, "token_type_hint": "access_token"},
                    auth=(self._client_id, self._client_secret),
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("active") is not True:
            return None

        issuer = payload.get("iss")
        if issuer is not None and str(issuer).rstrip("/") != self._issuer_url:
            return None

        audience = payload.get("aud")
        if audience:
            audiences = [str(audience)] if isinstance(audience, str) else [str(item) for item in audience]
            if self._resource_url not in audiences:
                return None

        expires_at: int | None = None
        if payload.get("exp") is not None:
            try:
                expires_at = int(payload["exp"])
            except (TypeError, ValueError):
                return None

        client_id = str(payload.get("client_id") or "oauth-client")
        scopes = _scope_list(payload.get("scope", payload.get("scopes", [])))
        subject = str(payload["sub"]) if payload.get("sub") is not None else None

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
            resource=self._resource_url,
            subject=subject,
            claims={"iss": str(issuer or self._issuer_url)},
        )


@dataclass(frozen=True, slots=True)
class PersonalAuthBundle:
    mode: str
    verifier: TokenVerifier
    settings: AuthSettings


def load_personal_auth_from_env() -> PersonalAuthBundle:
    """Build fail-closed auth for the remote Personal MCP endpoint.

    `oauth` is the production/ChatGPT mode. `static` exists only for trusted
    private smoke tests. There is deliberately no unauthenticated remote mode.
    """

    mode = os.getenv("TELEGRAM_MCP_AUTH_MODE", "oauth").strip().lower()
    resource_url = _required("TELEGRAM_MCP_PUBLIC_URL")
    scopes = _scopes_from_env()

    if mode == "oauth":
        issuer_url = _required("TELEGRAM_OAUTH_ISSUER_URL")
        verifier: TokenVerifier = IntrospectionTokenVerifier(
            introspection_url=_required("TELEGRAM_OAUTH_INTROSPECTION_URL"),
            client_id=_required("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID"),
            client_secret=_required("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET"),
            issuer_url=issuer_url,
            resource_url=resource_url,
        )
    elif mode == "static":
        issuer_url = os.getenv("TELEGRAM_MCP_STATIC_ISSUER_URL", "https://auth.invalid").strip()
        verifier = StaticTokenVerifier(_required("TELEGRAM_MCP_STATIC_TOKEN"), scopes)
    else:
        raise ConfigurationError(
            "TELEGRAM_MCP_AUTH_MODE must be 'oauth' or 'static'; remote unauthenticated mode is disabled"
        )

    settings = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(resource_url),
        required_scopes=scopes,
    )
    return PersonalAuthBundle(mode=mode, verifier=verifier, settings=settings)
