/**
 * FinalSubmission — 后门阶段的确定性四选一判断
 */

"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Send } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { useGameStore } from "@/stores/gameStore";

type JudgmentOption = "A" | "B" | "C" | "D";

const options: Array<{ id: JudgmentOption; text: string }> = [
  {
    id: "A",
    text: "陈吉在21:13从后门进入，目的是偷走旧账本。",
  },
  {
    id: "B",
    text: "王大达伪造便签，试图掩盖自己与旧案的关系。",
  },
  {
    id: "C",
    text: "王大达关于没人来过的说法不完整；至少可确认后门在21:13半开，但不能确认开门者和目的。",
  },
  {
    id: "D",
    text: "后门异常证明饭馆当晚发生过犯罪。",
  },
];

interface JudgmentResult {
  correct: boolean;
  score: number;
  detail: {
    evidence_boundary: string;
    npc_disclosure: string | null;
  };
}

interface FinalSubmissionProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: JudgmentResult) => void;
}

export function FinalSubmission({
  open,
  onClose,
  onComplete,
}: FinalSubmissionProps) {
  const sessionId = useGameStore((state) => state.sessionId);
  const [option, setOption] = useState<JudgmentOption | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleSubmit = async () => {
    if (!sessionId || !option || submitting) return;

    setShowConfirm(false);
    setSubmitting(true);
    try {
      const result = await api.submitFinal(sessionId, { option });
      toast(result.correct ? "判断成立" : "判断超出证据边界", {
        description: result.detail.evidence_boundary,
        icon: result.correct ? "✓" : "⚠️",
      });
      onComplete?.(result);
    } catch (error) {
      console.error("[FinalSubmission] 提交判断失败:", error);
      toast.error("判断提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-center justify-center p-4"
        >
          <div
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={submitting ? undefined : onClose}
          />

          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 30 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 30 }}
            transition={{ type: "spring", damping: 20 }}
            className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-6"
          >
            <div className="mb-6 text-center">
              <h2 className="mb-1 text-2xl font-bold">后门判断</h2>
              <p className="text-sm text-[var(--muted-foreground)]">
                根据当前材料，哪项最符合已证实事实？
              </p>
            </div>

            <div className="space-y-3">
              {options.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setOption(item.id)}
                  disabled={submitting}
                  className={`flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-all ${
                    option === item.id
                      ? "border-[var(--theme-primary)] bg-[var(--theme-primary)]/10"
                      : "border-[var(--border)] hover:bg-[var(--accent)]"
                  }`}
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-current text-xs font-bold">
                    {item.id}
                  </span>
                  <span className="text-sm leading-relaxed">{item.text}</span>
                </button>
              ))}
            </div>

            <button
              onClick={() => setShowConfirm(true)}
              disabled={!option || submitting}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--theme-primary)] py-3 font-bold transition-all hover:bg-[var(--theme-primary)]/80 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {submitting ? "提交中…" : "提交判断"}
            </button>
            <p className="mt-2 text-center text-[10px] text-[var(--muted-foreground)]">
              只判断材料能够证实到哪一步，不补全材料之外的剧情。
            </p>
          </motion.div>

          <AnimatePresence>
            {showConfirm && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[90] flex items-center justify-center p-4"
                onClick={() => setShowConfirm(false)}
              >
                <div className="absolute inset-0 bg-black/60" />
                <motion.div
                  initial={{ scale: 0.9 }}
                  animate={{ scale: 1 }}
                  exit={{ scale: 0.9 }}
                  onClick={(event) => event.stopPropagation()}
                  className="relative w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-6 text-center"
                >
                  <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-[var(--warning)]" />
                  <h3 className="mb-2 text-lg font-bold">确认提交选项 {option}？</h3>
                  <p className="mb-6 text-sm text-[var(--muted-foreground)]">
                    提交后将生成本次阶段判断的复盘结果。
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setShowConfirm(false)}
                      className="flex-1 rounded-lg border border-[var(--border)] py-2.5 text-sm"
                    >
                      再想想
                    </button>
                    <button
                      onClick={handleSubmit}
                      className="flex-1 rounded-lg bg-[var(--theme-primary)] py-2.5 text-sm font-bold"
                    >
                      确认提交
                    </button>
                  </div>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
