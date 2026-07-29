"use client";

import { AlertTriangle, Check, ChevronLeft, RotateCcw, Share2, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";

import type { Review } from "@/lib/game/types";

export function LegacyReview({ review }: { review: Review }) {
  const router = useRouter();
  const ratingColor = review.rating === "S"
    ? "text-yellow-300"
    : review.rating === "A"
      ? "text-emerald-300"
      : review.rating === "B"
        ? "text-sky-300"
        : "text-[#aeb1ab]";

  return (
    <div className="min-h-screen bg-[var(--background)] pb-16 text-[var(--foreground)]">
      <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--background)]/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <button
            type="button"
            onClick={() => router.push("/library")}
            className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <ChevronLeft className="h-4 w-4" />
            返回
          </button>
          <h1 className="text-sm font-bold">案件复盘</h1>
          <div className="w-12" />
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-4 py-8">
        <section className="mb-6 border border-[var(--border)] p-8 text-center">
          <p className={`text-6xl font-bold ${ratingColor}`}>{review.score}</p>
          <p className={`mt-2 text-lg font-semibold ${ratingColor}`}>{review.rating} 级</p>
          <p className="mt-3 text-sm text-[var(--muted-foreground)]">
            用时 {review.duration_minutes} 分钟 · 共 {review.breakdown.total_clues_available} 条线索
          </p>
        </section>

        <div className="mb-6 grid grid-cols-2 gap-3">
          <section className="border border-[var(--success)]/30 bg-[var(--success)]/5 p-4">
            <h2 className="mb-3 flex items-center gap-1.5 text-sm font-bold text-[var(--success)]">
              <Check className="h-4 w-4" />正确
            </h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span>真凶</span><span>{review.breakdown.suspect_correct ? "✓" : "✗"}</span></div>
              <div className="flex justify-between"><span>动机</span><span>{review.breakdown.motive_correct ? "✓" : "✗"}</span></div>
              <div className="flex justify-between"><span>证据命中率</span><span>{review.breakdown.key_evidence_hit_rate}</span></div>
            </div>
          </section>
          <section className="border border-[var(--warning)]/30 bg-[var(--warning)]/5 p-4">
            <h2 className="mb-3 flex items-center gap-1.5 text-sm font-bold text-[var(--warning)]">
              <AlertTriangle className="h-4 w-4" />遗漏
            </h2>
            {review.missed_key_clues.length > 0 ? (
              <div className="space-y-2 text-sm">
                {review.missed_key_clues.map((clue) => <p key={clue.id}>{clue.name}</p>)}
              </div>
            ) : <p className="text-xs text-[var(--muted-foreground)]">没有遗漏关键线索</p>}
            <p className="mt-3 border-t border-[var(--border)]/50 pt-2 text-sm">提示使用：{review.breakdown.hints_used} 次</p>
          </section>
        </div>

        <section className="mb-6 border border-[var(--border)] p-4">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-bold">
            <TrendingUp className="h-4 w-4 text-[var(--theme-primary)]" />线索覆盖
          </h2>
          <p className="text-sm text-[var(--muted-foreground)]">
            {review.breakdown.total_clues_found}/{review.breakdown.total_clues_available}（{review.breakdown.clue_coverage}）
          </p>
        </section>

        <section className="mb-6 border border-[var(--border)] p-4">
          <h2 className="mb-3 text-sm font-bold">推理路径</h2>
          <div className="space-y-4 text-sm">
            <div><p className="mb-1 text-xs text-[var(--muted-foreground)]">你的路径</p><p>{review.player_path.join(" → ") || "无数据"}</p></div>
            <div><p className="mb-1 text-xs text-[var(--muted-foreground)]">最优路径</p><p>{review.optimal_path.join(" → ") || "无数据"}</p></div>
          </div>
        </section>

        <section className="mb-8 border border-[var(--border)] p-4">
          <h2 className="mb-3 text-sm font-bold">真相摘要</h2>
          <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">{review.truth_summary}</p>
        </section>

        <div className="flex justify-center gap-3">
          <button
            type="button"
            onClick={() => router.push("/library")}
            className="flex items-center gap-2 border border-[var(--border)] px-6 py-3 text-sm transition-colors hover:bg-[var(--accent)]"
          >
            <RotateCcw className="h-4 w-4" />再来一次
          </button>
          <button
            type="button"
            className="flex items-center gap-2 bg-[var(--theme-primary)] px-6 py-3 text-sm font-bold transition-colors hover:opacity-80"
          >
            <Share2 className="h-4 w-4" />分享结果
          </button>
        </div>
      </div>
    </div>
  );
}
