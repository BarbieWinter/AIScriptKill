from pydantic import Field

from engine.api.schemas.common import ApiModel

# ── 线索查询 ──


class Clue(ApiModel):
    id: str = Field(description="Clue ID.")
    name: str = Field(description="Clue display name.")
    image_url: str = Field(description="Storage URL.")
    description: str = Field(description="Visible clue text.")
    is_key: bool = Field(description="Whether clue is key evidence.")
    importance: int = Field(description="Importance level.")
    discovered_at: str = Field(description="Discovery timestamp.")
    status: str = Field(description="Clue state.")


class ClueListResponse(ApiModel):
    clues: list[Clue] = Field(description="Unlocked clues.")


# ── 证物查询 ──


class Evidence(ApiModel):
    id: str = Field(description="Evidence ID.")
    name: str = Field(description="Evidence display name.")
    image_url: str = Field(description="Storage URL.")
    description: str = Field(description="Visible evidence text.")
    status: str = Field(description="Evidence state.")
    can_show_to_npc: bool = Field(description="Whether evidence can be shown.")
    shown_to_characters: list[str] = Field(description="Character IDs already shown.")


class EvidenceListResponse(ApiModel):
    evidences: list[Evidence] = Field(description="Discovered evidences.")


# ── 角色查询 ──


class CharacterSummary(ApiModel):
    id: str = Field(description="Character ID.")
    name: str = Field(description="Character display name.")
    portrait_url: str = Field(description="Portrait storage URL.")
    current_mood: str = Field(description="Current mood label.")
    mood_description: str = Field(description="Human-readable mood.")
    dialogue_available: bool = Field(description="Whether dialogue is available.")


class CharacterListResponse(ApiModel):
    characters: list[CharacterSummary] = Field(description="Current scene characters.")


# ── 聊天记录查询 ──


class ChatMessage(ApiModel):
    id: str = Field(description="Message ID.")
    role: str = Field(description="player, npc, or dm.")
    character_id: str | None = Field(description="NPC character ID when present.")
    text: str = Field(description="Message text.")
    timestamp: str = Field(description="Message timestamp.")
    emotion: str | None = Field(default=None, description="Optional emotion label.")


class ChatHistoryResponse(ApiModel):
    messages: list[ChatMessage] = Field(description="Chat messages.")
    next_page_token: str | None = Field(description="Pagination token.")


# ── 卡牌查询 ──


class Card(ApiModel):
    id: str = Field(description="Card ID.")
    name: str = Field(description="Card display name.")
    type: str = Field(description="Card type.")
    image_url: str = Field(description="Storage URL.")
    description: str = Field(description="Card effect text.")
    max_uses: int = Field(description="Maximum use count.")
    remaining_uses: int = Field(description="Remaining use count.")
    available: bool = Field(description="Whether card can be used now.")


class CardListResponse(ApiModel):
    cards: list[Card] = Field(description="Available cards.")
