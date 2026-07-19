"""提供 MP-2 Multiplayer v1 rollout gate。"""

from engine.api.config import get_settings
from engine.api.errors import service_unavailable


def require_multiplayer_enabled() -> None:
    """在 feature flag 关闭时稳定拒绝所有 multiplayer 能力。"""

    if not get_settings().multiplayer_v1:
        raise service_unavailable(
            "MULTIPLAYER_DISABLED",
            "Multiplayer v1 当前未启用",
        )
