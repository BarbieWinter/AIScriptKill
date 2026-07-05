from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, ClassVar, Literal, cast

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.api.config import get_settings
from engine.api.errors import unauthorized

# ── Bearer Token 入口 ──

bearer_scheme = HTTPBearer(auto_error=False)


# ── Supabase JWT Claims ──


class SupabaseClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True)

    sub: str = Field(description="Supabase Auth user ID.")
    role: str | None = Field(default=None, description="Supabase Postgres role.")


@dataclass(frozen=True, slots=True)
class CurrentUser:
    subject: str
    role: Literal["anonymous", "authenticated"]


# ── Supabase JWKS 校验器 ──


class SupabaseJwtVerifier:
    _jwks_client: PyJWKClient

    def __init__(self, supabase_url: str) -> None:
        jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        self._jwks_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> SupabaseClaims:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            key = cast(str | bytes, signing_key.key)
            decoded_claims = jwt.decode(
                jwt=token,
                key=key,
                algorithms=["RS256", "ES256"],
                options={"verify_aud": False},
            )
            return SupabaseClaims.model_validate(decoded_claims)
        except (InvalidTokenError, PyJWKClientError, ValidationError) as exc:
            raise unauthorized("INVALID_TOKEN", "无效的 Supabase JWT") from exc


# ── 鉴权依赖 ──


@lru_cache
def get_jwt_verifier() -> SupabaseJwtVerifier:
    settings = get_settings()
    return SupabaseJwtVerifier(settings.supabase_url)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> CurrentUser:
    if credentials is None:
        return CurrentUser(subject="anonymous", role="anonymous")

    verifier = get_jwt_verifier()
    claims = verifier.verify(credentials.credentials)
    return CurrentUser(subject=claims.sub, role="authenticated")


# ── 路由依赖别名 ──

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
