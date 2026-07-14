"""定义已过滤剧透内容的会话查询响应模型。"""

from pydantic import Field

from engine.api.schemas.common import ApiModel

# ── 线索查询 ──


class Clue(ApiModel):
    """公开当前会话已解锁的一条线索。"""

    id: str = Field(description="Clue ID.")
    name: str = Field(description="Clue display name.")
    image_url: str = Field(description="Storage URL.")
    description: str = Field(description="Visible clue text.")
    is_key: bool = Field(description="Whether clue is key evidence.")
    importance: int = Field(description="Importance level.")
    discovered_at: str = Field(description="Discovery timestamp.")
    status: str = Field(description="Clue state.")


class ClueListResponse(ApiModel):
    """返回当前会话可见的线索。"""

    clues: list[Clue] = Field(description="Unlocked clues.")


# ── 证物查询 ──


class Evidence(ApiModel):
    """公开当前会话已发现的一件证物。"""

    id: str = Field(description="Evidence ID.")
    name: str = Field(description="Evidence display name.")
    image_url: str = Field(description="Storage URL.")
    description: str = Field(description="Visible evidence text.")
    status: str = Field(description="Evidence state.")
    can_show_to_npc: bool = Field(description="Whether evidence can be shown.")
    shown_to_characters: list[str] = Field(description="Character IDs already shown.")


class EvidenceListResponse(ApiModel):
    """返回当前会话已发现的证物。"""

    evidences: list[Evidence] = Field(description="Discovered evidences.")


class EvidenceViewedResponse(ApiModel):
    """确认已发现证物进入已查看状态。"""

    evidence_id: str = Field(description="Viewed evidence ID.")
    status: str = Field(description="Monotonic evidence status.")


# ── 人物章节查询 ──


class CharacterChapterSummary(ApiModel):
    """公开玩家角色已解锁章节的目录信息。"""

    id: str = Field(description="Character chapter ID.")
    character_id: str = Field(description="Owning player character ID.")
    order: int = Field(description="Chapter display order.")
    title: str = Field(description="Chapter title.")
    status: str = Field(description="Unlocked or viewed status.")


class CharacterChapterListResponse(ApiModel):
    """返回当前玩家角色已解锁的章节目录。"""

    chapters: list[CharacterChapterSummary] = Field(description="Unlocked chapters.")


class CharacterChapterResponse(CharacterChapterSummary):
    """公开一个已授权人物章节的正文。"""

    content: str = Field(description="Authorized Markdown chapter body.")


# ── 角色查询 ──


class CharacterSummary(ApiModel):
    """公开玩家当前可用的一个角色。"""

    id: str = Field(description="Character ID.")
    name: str = Field(description="Character display name.")
    portrait_url: str = Field(description="Portrait storage URL.")
    current_mood: str = Field(description="Current mood label.")
    mood_description: str = Field(description="Human-readable mood.")
    dialogue_available: bool = Field(description="Whether dialogue is available.")


class CharacterListResponse(ApiModel):
    """返回当前会话场景中的可用角色。"""

    characters: list[CharacterSummary] = Field(description="Current scene characters.")


# ── 聊天记录查询 ──


class ChatMessage(ApiModel):
    """公开一条已持久化的玩家、NPC 或 DM 聊天消息。"""

    id: str = Field(description="Message ID.")
    role: str = Field(description="player, npc, or dm.")
    character_id: str | None = Field(description="NPC character ID when present.")
    text: str = Field(description="Message text.")
    timestamp: str = Field(description="Message timestamp.")
    emotion: str | None = Field(default=None, description="Optional emotion label.")


class ChatHistoryResponse(ApiModel):
    """返回一页会话聊天消息及其续传令牌。"""

    messages: list[ChatMessage] = Field(description="Chat messages.")
    next_page_token: str | None = Field(description="Pagination token.")


# ── 卡牌查询 ──


class Card(ApiModel):
    """公开一张可用的技能卡或道具卡及其使用次数。"""

    id: str = Field(description="Card ID.")
    name: str = Field(description="Card display name.")
    type: str = Field(description="Card type.")
    image_url: str = Field(description="Storage URL.")
    description: str = Field(description="Card effect text.")
    max_uses: int = Field(description="Maximum use count.")
    remaining_uses: int = Field(description="Remaining use count.")
    available: bool = Field(description="Whether card can be used now.")


class CardListResponse(ApiModel):
    """返回当前会话可用的卡牌。"""

    cards: list[Card] = Field(description="Available cards.")
