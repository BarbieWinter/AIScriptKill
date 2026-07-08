"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { useGameStore } from "@/stores/gameStore";
import {
  ChevronLeft,
  Check,
  AlertTriangle,
  RotateCcw,
  Share2,
  TrendingUp,
} from "lucide-react";

/** 数字动画计数组件 */
function AnimatedNumber({ value, duration = 1.5 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let start = 0;
    const step = Math.ceil(value / (duration * 60));
    const timer = setInterval(() => {
      start += step;
      if (start >= value) {
        setDisplay(value);
        clearInterval(timer);
      } else {
        setDisplay(start);
      }
    }, 1000 / 60);
    return () => clearInterval(timer);
  }, [value, duration]);

  return <>{display}</>;
}

const pageTransition = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: "easeInOut" },
};

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0 },
};

export default function ReviewPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  const [review, setReview] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getReview(sessionId).then((data) => {
      setReview(data);
      setLoading(false);
    });
  }, [sessionId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-[var(--theme-primary)] border-t-transparent animate-spin mb-4" />
          <p className="text-sm text-[var(--muted-foreground)]">解析推理结果…</p>
        </div>
      </main>
    );
  }

  if (!review) {
    return (
      <main className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <p className="text-[var(--muted-foreground)]">复盘数据不可用</p>
      </main>
    );
  }

  const getRatingColor = (rating: string) => {
    switch (rating) {
      case "S":
        return "from-[var(--warning)] to-yellow-500";
      case "A":
        return "from-[var(--success)] to-green-500";
      case "B":
        return "from-[var(--info)] to-blue-500";
      default:
        return "from-[var(--muted-foreground)] to-[var(--muted)]";
    }
  };

  return (
    <motion.main
      {...pageTransition}
      className="min-h-screen bg-[var(--background)] pb-16"
    >
      {/* 顶部 */}
      <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--background)]/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <button
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
        {/* 评分总览 */}
        <motion.section
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, type: "spring" }}
          className="mb-6 rounded-2xl border border-[var(--border)] p-8 text-center overflow-hidden relative"
        >
          {/* 背景渐变 */}
          <div
            className={`absolute inset-0 bg-gradient-to-b ${getRatingColor(review.rating)} opacity-5`}
          />

          <div className="relative">
            {/* 大数字动画 */}
            <motion.div
              initial={{ scale: 0.5 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", damping: 10, stiffness: 100 }}
              className="mb-2 text-6xl md:text-7xl font-bold text-[var(--theme-primary)]"
            >
              <AnimatedNumber value={review.score} />
            </motion.div>

            {/* 评级 */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
              className="mb-3"
            >
              <span
                className={`inline-block rounded-full bg-gradient-to-r ${getRatingColor(review.rating)} px-4 py-1 text-sm font-bold text-white`}
              >
                {review.rating} 级
              </span>
            </motion.div>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1 }}
              className="text-sm text-[var(--muted-foreground)]"
            >
              用时 {review.duration_minutes} 分钟 · 共 {review.breakdown?.total_clues_available || 9} 条线索
            </motion.p>
          </div>
        </motion.section>

        {/* 正确 / 遗漏 */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="mb-6 grid grid-cols-2 gap-3"
        >
          {/* 正确 */}
          <motion.section
            variants={itemVariants}
            className="rounded-xl border border-[var(--success)]/30 bg-[var(--success)]/5 p-4"
          >
            <h3 className="flex items-center gap-1.5 mb-3 text-sm font-bold text-[var(--success)]">
              <Check className="h-4 w-4" />
              正确
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-[var(--muted-foreground)]">真凶</span>
                <span className="font-bold">
                  {review.breakdown?.suspect_correct ? "✓" : "✗"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[var(--muted-foreground)]">动机</span>
                <span className="font-bold">
                  {review.breakdown?.motive_correct ? "✓" : "✗"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[var(--muted-foreground)]">证据命中率</span>
                <span className="font-bold">{review.breakdown?.key_evidence_hit_rate || "-"}</span>
              </div>
            </div>
          </motion.section>

          {/* 遗漏 */}
          <motion.section
            variants={itemVariants}
            className="rounded-xl border border-[var(--warning)]/30 bg-[var(--warning)]/5 p-4"
          >
            <h3 className="flex items-center gap-1.5 mb-3 text-sm font-bold text-[var(--warning)]">
              <AlertTriangle className="h-4 w-4" />
              遗漏
            </h3>
            <div className="space-y-2 text-sm">
              {review.missed_key_clues?.length > 0 ? (
                review.missed_key_clues.map((clue: any) => (
                  <div key={clue.id} className="text-[var(--muted-foreground)]">
                    <p className="text-xs">
                      ⚠ {clue.name}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-xs text-[var(--muted-foreground)]">没有遗漏关键线索</p>
              )}
              <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]/50">
                <span className="text-[var(--muted-foreground)]">提示使用</span>
                <span>{review.breakdown?.hints_used || 0} 次</span>
              </div>
            </div>
          </motion.section>
        </motion.div>

        {/* 探索覆盖 */}
        <motion.section
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="mb-6 rounded-xl border border-[var(--border)] p-4"
        >
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-[var(--theme-primary)]" />
              线索覆盖
            </h3>
            <span className="text-xs text-[var(--muted-foreground)]">
              {review.breakdown?.total_clues_found || 0}/{review.breakdown?.total_clues_available || 9}
            </span>
          </div>
          <div className="h-2 rounded-full bg-[var(--muted)] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{
                width: `${((review.breakdown?.total_clues_found || 0) / (review.breakdown?.total_clues_available || 9)) * 100}%`,
              }}
              transition={{ duration: 1, ease: "easeOut" }}
              className="h-full rounded-full bg-gradient-to-r from-[var(--theme-primary)] to-[var(--theme-accent)]"
            />
          </div>
        </motion.section>

        {/* 推理路径 */}
        <motion.section
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="mb-6 rounded-xl border border-[var(--border)] p-4"
        >
          <h3 className="text-sm font-bold mb-3">推理路径</h3>
          <div className="space-y-3">
            <div>
              <p className="text-xs text-[var(--muted-foreground)] mb-1">你的路径</p>
              <div className="flex flex-wrap gap-1.5">
                {review.player_path?.length > 0 ? (
                  review.player_path.map((step: string, i: number) => (
                    <span
                      key={step}
                      className="rounded-full bg-[var(--accent)] px-2.5 py-0.5 text-[10px] border border-[var(--border)]"
                    >
                      {i > 0 && "→ "}
                      {step}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-[var(--muted-foreground)]">无数据</span>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs text-[var(--muted-foreground)] mb-1">最优路径</p>
              <div className="flex flex-wrap gap-1.5">
                {review.optimal_path?.map((step: string, i: number) => (
                  <span
                    key={step}
                    className="rounded-full bg-[var(--theme-primary)]/10 px-2.5 py-0.5 text-[10px] border border-[var(--theme-primary)]/30"
                  >
                    {i > 0 && "→ "}
                    {step}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </motion.section>

        {/* 真相摘要 */}
        <motion.section
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          className="mb-8 rounded-xl border border-[var(--border)] p-4"
        >
          <h3 className="text-sm font-bold mb-3">真相摘要</h3>
          <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
            {review.truth_summary}
          </p>
        </motion.section>

        {/* 操作按钮 */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
          className="flex justify-center gap-3"
        >
          <button
            onClick={() => router.push("/library")}
            className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-6 py-3 text-sm transition-colors hover:bg-[var(--accent)]"
          >
            <RotateCcw className="h-4 w-4" />
            再来一次
          </button>
          <button className="flex items-center gap-2 rounded-xl bg-[var(--theme-primary)] px-6 py-3 text-sm font-bold transition-colors hover:bg-[var(--theme-primary)]/80">
            <Share2 className="h-4 w-4" />
            分享结果
          </button>
        </motion.div>
      </div>
    </motion.main>
  );
}
