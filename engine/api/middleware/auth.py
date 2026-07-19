"""使用已配置的 JWT 策略认证 HTTP 和 WebSocket 请求。"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, ClassVar, Final, Literal, cast
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.api.config import get_settings
from engine.api.errors import forbidden, unauthorized

# ── Bearer Token 入口 ──

bearer_scheme = HTTPBearer(auto_error=False)
ADMIN_APP_ROLES: Final[frozenset[str]] = frozenset({"admin", "owner"})


# ── Supabase JWT 声明 ──


class SupabaseAppMetadata(BaseModel):
    """从 Supabase JWT 元数据中解析服务端管理的应用角色。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    role: str | None = Field(default=None, description="Server-managed app role.")
    roles: tuple[str, ...] = Field(default=(), description="Server-managed app roles.")


class SupabaseClaims(BaseModel):
    """校验已验证 Supabase 访问令牌中的必要声明。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", frozen=True)

    sub: str = Field(description="Supabase Auth user ID.")
    exp: int = Field(description="JWT expiration timestamp.")
    role: str | None = Field(default=None, description="Supabase Postgres role.")
    is_anonymous: bool = Field(
        default=False,
        description="Whether Supabase Auth issued an anonymous-user access token.",
    )
    app_metadata: SupabaseAppMetadata = Field(
        default_factory=SupabaseAppMetadata,
        description="Supabase server-managed authorization metadata.",
    )


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """表示匿名调用方或已验证的 Supabase 用户。"""

    subject: str
    role: Literal["anonymous", "authenticated"]
    is_anonymous: bool = False
    app_role: str | None = None
    app_roles: tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        """返回服务端管理的元数据是否授予管理员角色。"""

        return self.app_role in ADMIN_APP_ROLES or bool(
            ADMIN_APP_ROLES.intersection(self.app_roles)
        )


@dataclass(frozen=True, slots=True)
class VerifiedAnonymousPrincipal:
    """仅携带经过验证的 Supabase anonymous principal UUID。"""

    id: UUID


# ── Supabase JWKS 校验器 ──


class SupabaseJwtVerifier:
    """校验 JWT 签名、签发方、受众、有效期和必要声明。"""

    _jwks_client: PyJWKClient
    _audience: str
    _issuer: str

    def __init__(self, supabase_url: str, audience: str) -> None:
        jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        self._jwks_client = PyJWKClient(jwks_url)
        self._audience = audience
        self._issuer = f"{supabase_url.rstrip('/')}/auth/v1"

    def verify(self, token: str) -> SupabaseClaims:
        """返回已验证的声明，失败时抛出稳定的 INVALID_TOKEN API 错误。"""

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            key = cast(str | bytes, signing_key.key)
            decoded_claims = jwt.decode(
                jwt=token,
                key=key,
                algorithms=["RS256", "ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["aud", "exp", "iss", "sub"]},
            )
            return SupabaseClaims.model_validate(decoded_claims)
        except (InvalidTokenError, PyJWKClientError, ValidationError) as exc:
            raise unauthorized("INVALID_TOKEN", "无效的 Supabase JWT") from exc


# ── 鉴权依赖 ──


@lru_cache
def get_jwt_verifier() -> SupabaseJwtVerifier:
    """返回与当前 Supabase 配置绑定的进程级缓存校验器。"""

    settings = get_settings()
    return SupabaseJwtVerifier(settings.supabase_url, settings.supabase_jwt_audience)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> CurrentUser:
    """将可选的 Bearer 凭证解析为匿名用户或已认证用户。"""

    if credentials is None:
        return CurrentUser(subject="anonymous", role="anonymous")

    verifier = get_jwt_verifier()
    claims = verifier.verify(credentials.credentials)
    return CurrentUser(
        subject=claims.sub,
        role="authenticated",
        is_anonymous=claims.is_anonymous,
        app_role=claims.app_metadata.role,
        app_roles=claims.app_metadata.roles,
    )


async def get_verified_anonymous_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> VerifiedAnonymousPrincipal:
    """要求一个由 Supabase 签发且 subject 为 UUID 的 anonymous access token。"""

    if credentials is None:
        raise unauthorized("AUTH_REQUIRED", "多人游戏需要匿名身份凭证")
    claims = get_jwt_verifier().verify(credentials.credentials)
    try:
        principal_id = UUID(claims.sub)
    except ValueError as exc:
        raise unauthorized("INVALID_USER_ID", "JWT 用户标识不是有效 UUID") from exc
    if not claims.is_anonymous:
        raise forbidden(
            "ANONYMOUS_IDENTITY_REQUIRED",
            "多人首版仅接受 Supabase anonymous 身份",
        )
    return VerifiedAnonymousPrincipal(id=principal_id)


async def require_verified_anonymous_principal(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> VerifiedAnonymousPrincipal:
    """将已验证的 optional auth 结果收窄为 multiplayer anonymous principal。"""

    if current_user.role == "anonymous":
        raise unauthorized("AUTH_REQUIRED", "多人游戏需要匿名身份凭证")
    try:
        principal_id = UUID(current_user.subject)
    except ValueError as exc:
        raise unauthorized("INVALID_USER_ID", "JWT 用户标识不是有效 UUID") from exc
    if not current_user.is_anonymous:
        raise forbidden(
            "ANONYMOUS_IDENTITY_REQUIRED",
            "多人首版仅接受 Supabase anonymous 身份",
        )
    return VerifiedAnonymousPrincipal(id=principal_id)


# ── 路由依赖别名 ──

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
VerifiedAnonymousPrincipalDep = Annotated[
    VerifiedAnonymousPrincipal,
    Depends(require_verified_anonymous_principal),
]


async def require_admin_user(current_user: CurrentUserDep) -> CurrentUser:
    """要求已认证的管理员元数据，否则抛出 401/403 API 错误。"""

    if current_user.role == "anonymous":
        raise unauthorized("AUTH_REQUIRED", "管理操作需要登录")
    if not current_user.is_admin:
        raise forbidden("ADMIN_REQUIRED", "管理操作需要管理员权限")
    return current_user


AdminUserDep = Annotated[CurrentUser, Depends(require_admin_user)]
