/**
 * TruthReveal - 阶段判断结果动画
 * 全屏覆盖，打字机效果展示证据边界复盘
 */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface TruthRevealProps {
  open: boolean;
  truthSummary: string;
  score?: number;
  rating?: string;
  sessionId?: string | null;
  onComplete?: () => void;
}

/** 逐字显示文本 */
function TypewriterText({ text, onComplete }: { text: string; onComplete: () => void }) {
  const [displayed, setDisplayed] = useState("");
  const [charIndex, setCharIndex] = useState(0);

  useEffect(() => {
    if (charIndex < text.length) {
      const timer = setTimeout(() => {
        setDisplayed(text.slice(0, charIndex + 1));
        setCharIndex(charIndex + 1);
      }, 40); // 每 40ms 一个字
      return () => clearTimeout(timer);
    } else {
      onComplete();
    }
  }, [charIndex, text, onComplete]);

  return (
    <p className="text-lg leading-relaxed">
      {displayed}
      <motion.span
        animate={{ opacity: [1, 0] }}
        transition={{ duration: 0.5, repeat: Infinity }}
        className="text-[var(--theme-primary)]"
      >
        |
      </motion.span>
    </p>
  );
}

export function TruthReveal({
  open,
  truthSummary,
  sessionId,
  onComplete,
}: TruthRevealProps) {
  const router = useRouter();
  const [startTyping, setStartTyping] = useState(false);
  const [typingComplete, setTypingComplete] = useState(false);

  useEffect(() => {
    if (open) {
      // 先显示标题，再开始打字
      const timer = setTimeout(() => setStartTyping(true), 1500);
      return () => clearTimeout(timer);
    }
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.5 }}
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black"
        >
          {/* 背景渐变 */}
          <div className="absolute inset-0 bg-gradient-to-b from-[var(--theme-primary)]/10 via-transparent to-transparent" />

          <div className="relative max-w-2xl w-full px-6 text-center">
            {/* 阶段判断标题 */}
            <motion.h1
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className="text-5xl md:text-7xl font-bold mb-8 bg-gradient-to-r from-[var(--theme-primary)] to-[var(--theme-accent)] bg-clip-text text-transparent"
            >
              判断结果
            </motion.h1>

            {/* 打字机真相文本 */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8, duration: 0.5 }}
              className="text-left text-[var(--foreground)]"
            >
              {startTyping && (
                <TypewriterText
                  text={truthSummary}
                  onComplete={() => setTypingComplete(true)}
                />
              )}
            </motion.div>

            {/* 完成后的按钮 */}
            <AnimatePresence>
              {typingComplete && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5 }}
                  className="mt-8"
                >
                  <button
                    onClick={() => {
                      onComplete?.();
                      if (sessionId) {
                        router.push(`/play/${sessionId}/review`);
                      }
                    }}
                    className="rounded-xl bg-[var(--theme-primary)] px-8 py-3 font-bold transition-all hover:bg-[var(--theme-primary)]/80"
                  >
                    查看复盘 →
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
