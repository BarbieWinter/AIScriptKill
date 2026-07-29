import { BookOpen, Eye, ShieldCheck } from "lucide-react";
import Link from "next/link";

import type { CompletedReviewV1 } from "@/lib/multiplayer/types";

export function CompletedReview({
  review,
  returnHref = "/multiplayer",
  returnLabel = "返回多人入口",
}: {
  review: CompletedReviewV1;
  returnHref?: string;
  returnLabel?: string;
}) {
  return (
    <div className="space-y-6">
      <header className="rounded-2xl border border-emerald-300/20 bg-emerald-300/[0.05] p-6 text-center">
        <ShieldCheck className="mx-auto mb-3 text-emerald-300" />
        <p className="text-xs text-emerald-200/60">游戏完成</p>
        <h1 className="mt-1 text-2xl font-semibold">{review.ending.name}</h1>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[#c1c3bd]">
          {review.ending.outcome_text}
        </p>
      </header>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <Eye className="h-4 w-4 text-[#c9ae76]" />
          案件真相
        </h2>
        {review.truth.case_summary && (
          <p className="mb-5 whitespace-pre-wrap text-sm leading-7 text-[#c1c3bd]">
            {review.truth.case_summary}
          </p>
        )}
        <div className="space-y-3">
          {review.truth.timeline.map((item) => (
            <div
              key={`${item.time}-${item.event}`}
              className="grid gap-1 border-l border-[#c9ae76]/30 pl-4 sm:grid-cols-[6rem_1fr]"
            >
              <span className="text-xs text-[#c9ae76]">{item.time}</span>
              <span className="text-sm text-[#b8bbb4]">{item.event}</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <BookOpen className="h-4 w-4 text-[#c9ae76]" />
          双方角色章节
        </h2>
        <div className="space-y-5">
          {review.chapters.map((chapter) => (
            <article key={chapter.id}>
              <h3 className="mb-2 font-medium text-[#e3d8bd]">{chapter.title}</h3>
              <p className="whitespace-pre-wrap text-sm leading-7 text-[#aeb1ab]">
                {chapter.content}
              </p>
            </article>
          ))}
        </div>
      </section>

      <div className="text-center">
        <Link href={returnHref} className="text-sm text-[#9fa29c] hover:text-white">
          {returnLabel}
        </Link>
      </div>
    </div>
  );
}
