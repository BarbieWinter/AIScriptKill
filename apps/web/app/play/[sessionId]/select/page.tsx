/**
 * CharacterSelectPage — 首个垂直切片的固定玩家身份
 *
 * 真人玩家直接扮演卓司元。确认身份时由后端创建真实 Session，
 * Mock 模式则继续通过同一 API 客户端创建隔离的 Mock Session。
 */

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Check } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";

const character = {
  id: "zhuosiyuan",
  name: "卓司元",
  tag: "「我记得的，和王大达说的并不完全一样。」",
  personality: "克制 · 谨慎 · 熟悉雪乡",
  background:
    "你以卓司元的身份回到雪乡。旧日记忆并不完整，但饭馆后门留下的细节，让你开始重新审视熟人们共同保持的沉默。",
  color: "#22c55e",
  gradient: "from-emerald-900/40 via-emerald-800/20 to-transparent",
};

export default function CharacterSelectPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleSelect = async () => {
    if (loading) return;

    setLoading(true);
    try {
      const session = await api.createSession(
        "snow-village",
        character.id,
        character.name
      );
      toast("身份已确认", {
        description: `你将以${character.name}的身份进入雪乡`,
        icon: "🎭",
      });
      router.push(`/play/${session.session_id}`);
    } catch (error) {
      console.error("[CharacterSelectPage] 创建会话失败:", error);
      toast.error("无法创建游戏会话", {
        description: "请确认后端服务与雪乡剧本包已经就绪。",
      });
      setLoading(false);
    }
  };

  return (
    <main className="relative h-screen w-full overflow-hidden bg-[var(--background)]">
      <div
        className={`absolute inset-0 bg-gradient-to-b ${character.gradient}`}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-[var(--background)] via-transparent to-[var(--background)]/50" />
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `radial-gradient(ellipse at 50% 0%, ${character.color}11, transparent 60%)`,
        }}
      />

      <button
        onClick={() => router.back()}
        className="absolute top-4 left-4 z-20 flex h-9 w-9 items-center justify-center rounded-lg border border-white/5 bg-black/40 text-white/60 backdrop-blur-sm transition-all hover:text-white/90"
        aria-label="返回"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>

      <div className="relative z-10 flex h-full flex-col items-center justify-center px-6 pb-24">
        <motion.p
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-2 text-xs uppercase tracking-[0.2em] text-white/30"
        >
          你的身份
        </motion.p>

        <div className="relative mx-auto mb-8 w-full max-w-md">
          <div className="mb-6 flex justify-center">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", damping: 15, stiffness: 200 }}
              className="relative"
            >
              <div
                className="flex h-32 w-32 items-center justify-center rounded-full border-4 text-4xl md:h-40 md:w-40 md:text-5xl"
                style={{
                  borderColor: `${character.color}40`,
                  backgroundColor: `${character.color}10`,
                  boxShadow: `0 0 40px ${character.color}20`,
                }}
              >
                🔍
              </div>
              <div
                className="absolute inset-0 animate-ping rounded-full opacity-20"
                style={{ boxShadow: `0 0 30px ${character.color}` }}
              />
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="text-center"
          >
            <h2 className="mb-2 text-3xl font-bold text-white">
              {character.name}
            </h2>
            <p className="mb-4 text-sm italic text-white/50">
              {character.tag}
            </p>
            <div
              className="mb-4 inline-block rounded-full px-3 py-1 text-xs"
              style={{
                backgroundColor: `${character.color}15`,
                color: character.color,
              }}
            >
              {character.personality}
            </div>
            <p className="mx-auto max-w-md px-4 text-sm leading-relaxed text-white/40">
              {character.background}
            </p>
          </motion.div>
        </div>

        <motion.button
          onClick={handleSelect}
          disabled={loading}
          whileHover={{ scale: loading ? 1 : 1.02 }}
          whileTap={{ scale: loading ? 1 : 0.98 }}
          className="relative flex items-center gap-3 rounded-xl bg-[var(--theme-primary)] px-10 py-3.5 text-sm font-bold text-white shadow-xl shadow-[var(--theme-primary)]/20 transition-all hover:bg-[var(--theme-primary)]/80 disabled:opacity-60"
        >
          {loading ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              创建会话中…
            </>
          ) : (
            <>
              <Check className="h-4 w-4" />
              以卓司元的身份开始
            </>
          )}
        </motion.button>
      </div>
    </main>
  );
}
