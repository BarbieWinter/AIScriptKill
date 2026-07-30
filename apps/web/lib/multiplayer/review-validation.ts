import type { CompletedReviewV1 } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isBallotArray(value: unknown): boolean {
  return Array.isArray(value)
    && value.length > 0
    && value.every((ballot) => (
      isRecord(ballot)
      && typeof ballot.member_id === "string"
      && typeof ballot.option_id === "string"
    ));
}

function isOptionCountArray(value: unknown): boolean {
  return Array.isArray(value)
    && value.length > 0
    && value.every((count) => (
      isRecord(count)
      && typeof count.option_id === "string"
      && typeof count.count === "number"
    ));
}

export function isCompletedReview(value: unknown): value is CompletedReviewV1 {
  if (!isRecord(value) || value.review_version !== 1) return false;
  const ending = value.ending;
  const truth = value.truth;
  const finalSettlement = value.final_settlement;
  if (!isRecord(ending) || !isRecord(truth) || !isRecord(finalSettlement)) return false;

  const chaptersValid = Array.isArray(value.chapters) && value.chapters.every((chapter) => (
    isRecord(chapter)
    && typeof chapter.id === "string"
    && typeof chapter.character_id === "string"
    && typeof chapter.title === "string"
    && typeof chapter.content === "string"
  ));
  const timelineValid = Array.isArray(truth.timeline) && truth.timeline.every((item) => (
    isRecord(item)
    && typeof item.time === "string"
    && typeof item.event === "string"
    && typeof item.hidden === "boolean"
  ));
  const alternativeEndingsValid = Array.isArray(truth.alternative_endings)
    && truth.alternative_endings.every((item) => (
      isRecord(item)
      && typeof item.id === "string"
      && typeof item.condition === "string"
      && isNullableString(item.news_broadcast)
    ));
  const settlementValid = finalSettlement.reveal === "named_ballots"
    ? isBallotArray(finalSettlement.ballots) && finalSettlement.option_counts === undefined
    : finalSettlement.reveal === "aggregate"
      ? isOptionCountArray(finalSettlement.option_counts) && finalSettlement.ballots === undefined
      : finalSettlement.reveal === "outcome_only"
        && finalSettlement.ballots === undefined
        && finalSettlement.option_counts === undefined;

  return typeof value.session_id === "string"
    && typeof value.member_id === "string"
    && typeof ending.id === "string"
    && typeof ending.name === "string"
    && typeof ending.outcome_text === "string"
    && chaptersValid
    && isNullableString(truth.case_summary)
    && isNullableString(truth.murderer)
    && isNullableString(truth.victim)
    && isNullableString(truth.motive)
    && timelineValid
    && isStringArray(truth.key_evidence_chain)
    && alternativeEndingsValid
    && typeof finalSettlement.stage_id === "string"
    && typeof finalSettlement.settlement_id === "string"
    && typeof finalSettlement.outcome_id === "string"
    && settlementValid;
}
