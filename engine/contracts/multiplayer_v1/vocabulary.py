"""定义 Multiplayer v1 的稳定领域词汇。"""

from enum import StrEnum


class RoomStatus(StrEnum):
    """房间生命周期状态。"""

    LOBBY = "lobby"
    ACTIVE = "active"
    COMPLETED = "completed"
    CLOSED = "closed"


class StagePhase(StrEnum):
    """一个多人阶段内的确定性子阶段。"""

    READ = "read"
    DISCUSS = "discuss"
    SETTLE = "settle"
    REVEAL = "reveal"


class DiscussionClosePolicy(StrEnum):
    """公共讨论结束所需的成员确认规则。"""

    ALL_PLAYERS = "all_players"


class FinalAnswerMode(StrEnum):
    """最终判断由房间共同选择或由成员分别秘密提交。"""

    SHARED_CHOICE = "shared_choice"
    INDIVIDUAL_SECRET = "individual_secret"


class SettlementMode(StrEnum):
    """阶段结算的协作或投票方式。"""

    NONE = "none"
    SECRET_VOTE = "secret_vote"
    SHARED_CHOICE = "shared_choice"
    FINAL_JUDGMENT = "final_judgment"


class CommandStatus(StrEnum):
    """命令执行结果状态。"""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AudienceScope(StrEnum):
    """事件可见范围。"""

    ROOM = "room"
    MEMBER = "member"


class SettlementReveal(StrEnum):
    """结算揭晓时允许公开的信息粒度。"""

    NAMED_BALLOTS = "named_ballots"
    AGGREGATE = "aggregate"
    OUTCOME_ONLY = "outcome_only"


class SubmissionChangePolicy(StrEnum):
    """结算提交完成前的改票规则。"""

    FORBIDDEN = "forbidden"
    ALLOWED_BEFORE_COMPLETE = "allowed_before_complete"


class SettlementEffect(StrEnum):
    """结算结果对剧本流程的默认作用。"""

    RECORD_AND_CONTINUE = "record_and_continue"
    BRANCH = "branch"


class CharacterAssignmentPolicy(StrEnum):
    """房间开始前的角色分配要求。"""

    REQUIRED = "required"


class StartPolicy(StrEnum):
    """房间开始条件。"""

    ALL_PLAYERS_READY = "all_players_ready"
