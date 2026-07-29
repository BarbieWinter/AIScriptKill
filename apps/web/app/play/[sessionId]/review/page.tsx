"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, CircleAlert, LoaderCircle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { CompletedReview } from "@/components/multiplayer/CompletedReview";
import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import {
  createMultiplayerRoomClient,
  multiplayerReviewKey,
} from "@/lib/multiplayer/room-client";

export default function ReviewPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = params.sessionId;
  const client = useMemo(() => createMultiplayerRoomClient(), []);
  const review = useQuery({
    queryKey: multiplayerReviewKey(sessionId),
    queryFn: ({ signal }) => client.getReview(sessionId, signal),
    retry: shouldRetryMultiplayer,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  return (
    <main className="min-h-screen bg-[#080a0c] text-[#e8e2d5]">
      <header className="border-b border-white/8 bg-[#0d100f]">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-4 px-5 py-4">
          <Link
            href={`/play/${sessionId}/lobby`}
            className="inline-flex items-center gap-2 text-sm text-[#a8aba5] hover:text-white"
          >
            <ChevronLeft className="h-4 w-4" />
            返回终局
          </Link>
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
            <CompletedReview
              review={review.data}
              returnHref="/multiplayer"
              returnLabel="返回多人入口"
            />
          </>
        )}
      </div>
    </main>
  );
}
