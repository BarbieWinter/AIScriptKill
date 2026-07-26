"""Build completed multiplayer review projections from frozen package content."""

from engine.contracts.multiplayer_v1.authoring import (
    FinalJudgmentSettlementDefinition,
    MultiplayerStageDefinition,
    NoSettlementDefinition,
)
from engine.contracts.multiplayer_v1.reviews import (
    REVIEW_VERSION,
    AggregateReview,
    CompletedReviewV1,
    NamedBallotsReview,
    OutcomeOnlyReview,
    ReviewAlternativeEnding,
    ReviewChapter,
    ReviewEnding,
    ReviewSettlementReveal,
    ReviewTimelineEntry,
    ReviewTruth,
)
from engine.contracts.multiplayer_v1.state import GameStateV2
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus, SettlementReveal
from engine.core.package_dm_guide import DmGuideFiles
from engine.core.package_schema import ScriptPackageImport


class CompletedReviewProjectionError(ValueError):
    """Raised when completed review inputs are incomplete or inconsistent."""


def project_completed_review(
    *,
    state: GameStateV2,
    member_id: str,
    package: ScriptPackageImport,
    final_definition: MultiplayerStageDefinition,
) -> CompletedReviewV1:
    """Project one participant-safe review from the room's decoded frozen package."""

    if state.room.status is not RoomStatus.COMPLETED:
        raise CompletedReviewProjectionError("completed review requires a completed room")
    if member_id not in state.room.required_member_ids:
        raise CompletedReviewProjectionError("completed review member must belong to the room")
    if state.ending_id is None:
        raise CompletedReviewProjectionError("completed review requires ending_id")
    if final_definition.id != state.stage.stage_id:
        raise CompletedReviewProjectionError(
            "final stage definition does not match completed state"
        )
    authored_settlement = final_definition.settlement
    runtime_settlement = state.stage.settlement
    if not isinstance(authored_settlement, FinalJudgmentSettlementDefinition):
        raise CompletedReviewProjectionError("completed review requires final judgment authoring")
    if (
        runtime_settlement is None
        or runtime_settlement.outcome_id is None
        or authored_settlement.ending_by_outcome.get(runtime_settlement.outcome_id)
        != state.ending_id
    ):
        raise CompletedReviewProjectionError(
            "completed ending must match the authored outcome mapping"
        )
    playable_character_ids = frozenset(
        player.character_id for player in state.players.values() if player.character_id is not None
    )
    if frozenset(final_definition.chapters) != playable_character_ids:
        raise CompletedReviewProjectionError(
            "final stage characters do not match completed room assignments"
        )

    matching_endings = tuple(ending for ending in package.endings if ending.id == state.ending_id)
    if len(matching_endings) != 1:
        raise CompletedReviewProjectionError(
            "completed ending must exist exactly once in the frozen package"
        )
    ending = matching_endings[0]
    outcome_text = ending.metadata.get("outcome_text", "")
    if not isinstance(outcome_text, str):
        raise CompletedReviewProjectionError("frozen ending outcome_text must be text")

    try:
        guide = DmGuideFiles.model_validate(package.dm_guide)
    except (TypeError, ValueError) as exc:
        raise CompletedReviewProjectionError("frozen truth content is invalid") from exc
    if guide.truth is None:
        raise CompletedReviewProjectionError("completed review requires frozen truth content")

    chapters = tuple(
        ReviewChapter(
            id=chapter.id,
            character_id=chapter.character_id,
            title=chapter.title,
            content=chapter.content,
        )
        for chapter in sorted(package.chapters, key=lambda item: (item.sort_order, item.id))
        if chapter.character_id in playable_character_ids
    )
    chapter_ids = tuple(chapter.id for chapter in chapters)
    if len(chapter_ids) != len(set(chapter_ids)):
        raise CompletedReviewProjectionError("frozen review chapters must have unique ids")
    chapter_character_ids = frozenset(chapter.character_id for chapter in chapters)
    if chapter_character_ids != playable_character_ids:
        raise CompletedReviewProjectionError(
            "frozen review chapters do not cover completed room characters"
        )

    truth = guide.truth.truth
    return CompletedReviewV1(
        review_version=REVIEW_VERSION,
        session_id=state.session_id,
        member_id=member_id,
        ending=ReviewEnding(
            id=ending.id,
            name=ending.name,
            outcome_text=outcome_text,
        ),
        chapters=chapters,
        truth=ReviewTruth(
            case_summary=truth.case_summary,
            murderer=truth.murderer,
            victim=truth.victim,
            motive=truth.motive,
            timeline=tuple(
                ReviewTimelineEntry(time=item.time, event=item.event, hidden=item.hidden)
                for item in truth.timeline
            ),
            key_evidence_chain=tuple(truth.key_evidence_chain),
            alternative_endings=tuple(
                ReviewAlternativeEnding(
                    id=item.id,
                    condition=item.condition,
                    news_broadcast=item.news_broadcast,
                )
                for item in truth.alternative_endings
            ),
        ),
        final_settlement=_project_final_settlement(
            state=state,
            definition=final_definition,
        ),
    )


def _project_final_settlement(
    *,
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
) -> ReviewSettlementReveal:
    runtime = state.stage.settlement
    authored = definition.settlement
    if isinstance(authored, NoSettlementDefinition):
        raise CompletedReviewProjectionError("completed review requires final settlement reveal")
    if (
        runtime is None
        or not runtime.revealed
        or runtime.outcome_id is None
        or runtime.settlement_id != authored.settlement_id
    ):
        raise CompletedReviewProjectionError("completed review requires final settlement reveal")

    common = {
        "stage_id": state.stage.stage_id,
        "settlement_id": runtime.settlement_id,
        "outcome_id": runtime.outcome_id,
    }
    if authored.reveal is SettlementReveal.NAMED_BALLOTS:
        if not runtime.revealed_ballots or runtime.revealed_option_counts:
            raise CompletedReviewProjectionError("named-ballot review facts are missing")
        return NamedBallotsReview(
            reveal="named_ballots",
            ballots=runtime.revealed_ballots,
            **common,
        )
    if authored.reveal is SettlementReveal.AGGREGATE:
        if not runtime.revealed_option_counts or runtime.revealed_ballots:
            raise CompletedReviewProjectionError("aggregate review facts are missing")
        return AggregateReview(
            reveal="aggregate",
            option_counts=runtime.revealed_option_counts,
            **common,
        )
    if runtime.revealed_ballots or runtime.revealed_option_counts:
        raise CompletedReviewProjectionError("outcome-only review must not expose vote details")
    return OutcomeOnlyReview(reveal="outcome_only", **common)
