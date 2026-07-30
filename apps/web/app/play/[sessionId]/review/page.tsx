"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, CircleAlert, LoaderCircle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { LegacyReview } from "@/components/game/LegacyReview";
import { CompletedReview } from "@/components/multiplayer/CompletedReview";
import { ApiError, api, isMockMode } from "@/lib/api";
import type { Review } from "@/lib/game/types";
import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import { isCompletedReview } from "@/lib/multiplayer/review-validation";
import {
  createMultiplayerRoomClient,
  multiplayerReviewKey,
} from "@/lib/multiplayer/room-client";
import type { CompletedReviewV1 } from "@/lib/multiplayer/types";

type ReviewData =
  | { kind: "multiplayer"; data: CompletedReviewV1 }
  | { kind: "legacy"; data: Review };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isLegacyReview(value: unknown): value is Review {
  if (!isRecord(value) || !isRecord(value.breakdown)) return false;
  const breakdown = value.breakdown;
  return typeof value.session_id === "string"
    && typeof value.script_id === "string"
    && typeof value.score === "number"
    && typeof value.max_score === "number"
    && typeof value.rating === "string"
    && typeof value.duration_minutes === "number"
    && typeof breakdown.suspect_correct === "boolean"
    && typeof breakdown.motive_correct === "boolean"
    && typeof breakdown.key_evidence_hit_rate === "string"
    && typeof breakdown.wrong_accusations === "number"
    && typeof breakdown.total_clues_found === "number"
    && typeof breakdown.total_clues_available === "number"
    && typeof breakdown.clue_coverage === "string"
    && typeof breakdown.hints_used === "number"
    && Array.isArray(value.missed_key_clues)
    && value.missed_key_clues.every((clue) => (
      isRecord(clue)
      && typeof clue.id === "string"
      && typeof clue.name === "string"
      && typeof clue.description === "string"
    ))
    && isStringArray(value.optimal_path)
    && isStringArray(value.player_path)
    && typeof value.truth_summary === "string";
}

const uuidSessionId = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function reviewPageKey(sessionId: string) {
  return ["review-page", sessionId] as const;
}

async function loadLegacyReview(sessionId: string, signal?: AbortSignal): Promise<ReviewData> {
  const payload = await api.getReview(sessionId, signal) as unknown;
  if (!isLegacyReview(payload)) throw new Error("旧版复盘数据格式无效。");
  return { kind: "legacy", data: payload };
}

export default function ReviewPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const client = useMemo(() => createMultiplayerRoomClient(), []);
  const queryClient = useQueryClient();
  const review = useQuery<ReviewData>({
    queryKey: reviewPageKey(sessionId),
    queryFn: async ({ signal }) => {
      if (isMockMode() && !uuidSessionId.test(sessionId)) {
        return loadLegacyReview(sessionId, signal);
      }

      try {
        return await loadLegacyReview(sessionId, signal);
      } catch (error) {
        if (signal.aborted) throw error;
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
      }

      const payload = await client.getReview(sessionId, signal) as unknown;
      if (isCompletedReview(payload)) {
        queryClient.setQueryData(
          multiplayerReviewKey(sessionId, payload.member_id),
          payload,
        );
        return { kind: "multiplayer", data: payload };
      }
      if (isLegacyReview(payload)) return { kind: "legacy", data: payload };
      throw new Error("复盘数据格式无效。");
    },
    retry: shouldRetryMultiplayer,
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const returnDestination = review.data
    ? review.data.kind === "legacy"
      ? { href: "/library", label: "返回剧本库" }
      : { href: `/play/${sessionId}/lobby`, label: "返回终局" }
    : null;

  return (
    <main className="min-h-screen bg-[#080a0c] text-[#e8e2d5]">
      <header className="border-b border-white/8 bg-[#0d100f]">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-5 py-4">
          <div className="min-w-[7rem]">
            {returnDestination && (
              <Link
                href={returnDestination.href}
                className="inline-flex items-center gap-2 text-sm text-[#a8aba5] hover:text-white"
              >
                <ChevronLeft className="h-4 w-4" />
                {returnDestination.label}
              </Link>
            )}
          </div>
          <p className="text-sm font-semibold">案件复盘</p>
          <button
            type="button"
            onClick={() => void review.refetch()}
            disabled={review.isFetching}
            className="inline-flex items-center gap-2 text-sm text-[#d8c28f] disabled:opacity-50"
          >
            <RotateCcw className={`h-4 w-4 ${review.isFetching ? "animate-spin" : ""}`} />
            刷新复盘
          </button>
        </div>
      </header>

      <div className="mx-auto w-full max-w-3xl px-5 py-8 md:py-12">
        {review.isPending && (
          <div className="py-24 text-center">
            <LoaderCircle className="mx-auto mb-4 h-8 w-8 animate-spin text-[#c9ae76]" />
            <p className="text-sm text-[#9fa29c]">正在读取终局复盘…</p>
          </div>
        )}

        {!review.data && review.isError && (
          <section className="mx-auto max-w-md border border-red-300/15 bg-[#111412] p-8 text-center">
            <CircleAlert className="mx-auto mb-5 h-8 w-8 text-red-300" />
            <h1 className="mb-2 text-xl font-semibold">无法读取复盘</h1>
            <div role="alert" className="mb-6 text-sm leading-6 text-[#b8bab4]">
              <p>{multiplayerErrorMessage(review.error)}</p>
              {multiplayerErrorCode(review.error) && (
                <p className="mt-2 font-mono text-[11px] text-red-200/60">
                  {multiplayerErrorCode(review.error)}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void review.refetch()}
              className="inline-flex w-full items-center justify-center gap-2 bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f]"
            >
              <RotateCcw className="h-4 w-4" />
              重新加载复盘
            </button>
          </section>
        )}

        {review.data && (
          <>
            {review.isError && (
              <div role="alert" className="mb-6 flex items-center gap-2 border border-amber-200/20 bg-amber-200/[0.06] px-4 py-3 text-sm text-amber-50">
                <CircleAlert className="h-4 w-4 shrink-0" />
                刷新失败，正在显示上次成功的复盘。
              </div>
            )}
            {review.data.kind === "multiplayer" ? (
              <CompletedReview
                review={review.data.data}
                returnHref="/multiplayer"
                returnLabel="返回多人入口"
              />
            ) : (
              <LegacyReview review={review.data.data} />
            )}
          </>
        )}
      </div>
    </main>
  );
}
