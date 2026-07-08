/**
 * StageTransition - 阶段切换横幅动画
 * 顶部滑入 → 停留 → 顶部滑出
 * 触发: stage.changed WebSocket 事件
 */

"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";

interface StageTransitionProps {
  stageName: string | null;
  reason?: string;
  onComplete?: () => void;
}

export function StageTransition({
  stageName,
  reason,
  onComplete,
}: StageTransitionProps) {
  const [visible, setVisible] = useState(false);
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [currentReason, setCurrentReason] = useState<string | undefined>();

  useEffect(() => {
    if (stageName && stageName !== currentStage) {
      setCurrentStage(stageName);
      setCurrentReason(reason);
      setVisible(true);

      // 3秒后滑出
      const timer = setTimeout(() => {
        setVisible(false);
        setTimeout(() => onComplete?.(), 500);
      }, 3000);

      return () => clearTimeout(timer);
    }
  }, [stageName, reason, currentStage, onComplete]);

  return (
    <AnimatePresence>
      {visible && currentStage && (
        <motion.div
          initial={{ y: -100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: -100, opacity: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="fixed top-0 left-0 right-0 z-[60] flex items-center justify-center"
        >
          <div className="mx-auto mt-4 w-full max-w-lg rounded-xl border border-[var(--theme-primary)]/30 bg-gradient-to-r from-[var(--theme-primary)]/20 via-[var(--background)] to-[var(--theme-primary)]/20 px-6 py-4 text-center backdrop-blur-xl shadow-2xl shadow-[var(--theme-primary)]/10">
            <div className="flex items-center justify-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-[var(--theme-primary)] animate-pulse" />
              <span className="text-xs font-bold tracking-widest text-[var(--theme-primary)] uppercase">
                阶段推进
              </span>
            </div>
            <h3 className="text-lg font-bold text-[var(--foreground)]">
              {currentStage}
            </h3>
            {currentReason && (
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                {currentReason}
              </p>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
