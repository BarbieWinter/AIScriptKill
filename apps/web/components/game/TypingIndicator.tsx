/**
 * TypingIndicator - NPC 打字指示器
 * 模拟 LLM 响应延迟的三个阶段：
 * 0-3s: 闪烁 "..."
 * 3-10s: "正在思索……" + 思考表情
 * >10s: "还在回忆中……" + 建议查看线索
 */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";

interface TypingIndicatorProps {
  characterName: string;
  startTime: number;
}

export function TypingIndicator({ characterName, startTime }: TypingIndicatorProps) {
  const [phase, setPhase] = useState<"typing" | "thinking" | "hint">("typing");

  useEffect(() => {
    const t1 = setTimeout(() => setPhase("thinking"), 3000);
    const t2 = setTimeout(() => setPhase("hint"), 10000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [startTime]);

  return (
    <AnimatePresence mode="wait">
      {phase === "typing" && (
        <motion.div
          key="typing"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex items-center gap-2 mb-3 ml-1"
        >
          {/* 头像脉动 */}
          <motion.div
            className="h-6 w-6 rounded-full bg-[var(--theme-primary)]/30"
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
          <div className="flex gap-1">
            <motion.span
              className="text-sm text-[var(--muted-foreground)]"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity }}
            >
              .
            </motion.span>
            <motion.span
              className="text-sm text-[var(--muted-foreground)]"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
            >
              .
            </motion.span>
            <motion.span
              className="text-sm text-[var(--muted-foreground)]"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}
            >
              .
            </motion.span>
          </div>
        </motion.div>
      )}

      {phase === "thinking" && (
        <motion.div
          key="thinking"
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="flex items-center gap-2 mb-3 ml-1 text-sm text-[var(--muted-foreground)]"
        >
          <span>🤔</span>
          <span>{characterName}正在思索……</span>
        </motion.div>
      )}

      {phase === "hint" && (
        <motion.div
          key="hint"
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="flex items-center gap-2 mb-3 ml-1 text-sm text-[var(--warning)]"
        >
          <span>💭</span>
          <span>还在回忆中，要不先看看其他线索？</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
