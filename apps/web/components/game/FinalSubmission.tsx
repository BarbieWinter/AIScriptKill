/**
 * FinalSubmission - 最终推理提交流
 * 全屏模态，包含指控对象、动机、证据选择、推理描述
 * 提交后有信封飞入动画和等待效果
 */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/stores/gameStore";
import { getMockEngine } from "@/lib/mock-data";
import { useRouter } from "next/navigation";
import { Send, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

interface FinalSubmissionProps {
  open: boolean;
  onClose: () => void;
  onComplete?: () => void;
}

export function FinalSubmission({ open, onClose, onComplete }: FinalSubmissionProps) {
  const router = useRouter();
  const sessionId = useGameStore((s) => s.sessionId);
  const evidences = useGameStore((s) => s.discoveredEvidences);
  const characters = useGameStore((s) => s.availableCharacters);

  const [suspect, setSuspect] = useState("");
  const [motive, setMotive] = useState("");
  const [keyEvidences, setKeyEvidences] = useState<string[]>([]);
  const [deduction, setDeduction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  // 嫌疑选项（来自可交互 NPC）
  const suspectOptions = characters.filter((c: any) => !c.is_dm_alter_ego && c.id !== "dm");

  const motiveOptions = [
    "复仇",
    "谋财",
    "情杀",
    "灭口",
    "误杀",
    "自卫",
  ];

  const toggleEvidence = (id: string) => {
    setKeyEvidences((prev) =>
      prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]
    );
  };

  /** 提交推理 */
  const handleSubmit = () => {
    if (!suspect || !motive || keyEvidences.length === 0) {
      toast.error("请填写完整推理信息");
      return;
    }
    setShowConfirm(false);
    setSubmitting(true);

    // 模拟提交延迟
    setTimeout(() => {
      const engine = getMockEngine();
      const submissionResult = engine.submitFinal({
        suspect,
        motive,
        key_evidences: keyEvidences,
        deduction,
      });
      setResult(submissionResult);
      setSubmitting(false);

      toast.success("推理已提交！");
      onComplete?.();

      // 延迟跳转到复盘
      setTimeout(() => {
        if (sessionId) {
          router.push(`/play/${sessionId}/review`);
        }
      }, 3000);
    }, 2500);
  };

  return (
    <AnimatePresence>
      {open && !result && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-center justify-center p-4"
        >
          <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />

          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 30 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 30 }}
            transition={{ type: "spring", damping: 20 }}
            className="relative max-w-lg w-full max-h-[90vh] overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-6"
          >
            {/* 标题 */}
            <div className="text-center mb-6">
              <h2 className="text-2xl font-bold mb-1">最终推理</h2>
              <p className="text-sm text-[var(--muted-foreground)]">
                根据你收集的线索，指认真相
              </p>
            </div>

            {/* 指控对象 */}
            <div className="mb-4">
              <label className="block text-xs font-bold text-[var(--muted-foreground)] mb-1.5">
                指控对象
              </label>
              <select
                value={suspect}
                onChange={(e) => setSuspect(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--accent)] px-3 py-2.5 text-sm outline-none focus:border-[var(--theme-primary)]"
              >
                <option value="">选择角色…</option>
                {suspectOptions.map((c: any) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            {/* 作案动机 */}
            <div className="mb-4">
              <label className="block text-xs font-bold text-[var(--muted-foreground)] mb-1.5">
                作案动机
              </label>
              <select
                value={motive}
                onChange={(e) => setMotive(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--accent)] px-3 py-2.5 text-sm outline-none focus:border-[var(--theme-primary)]"
              >
                <option value="">选择动机…</option>
                {motiveOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            {/* 关键证据 */}
            <div className="mb-4">
              <label className="block text-xs font-bold text-[var(--muted-foreground)] mb-1.5">
                关键证据（选择你的证据链）
              </label>
              <div className="space-y-2 max-h-32 overflow-y-auto">
                {evidences.length === 0 ? (
                  <p className="text-xs text-[var(--muted-foreground)]">尚未发现任何证物</p>
                ) : (
                  evidences.map((ev: any) => (
                    <label
                      key={ev.id}
                      className="flex items-center gap-3 rounded-lg border border-[var(--border)] px-3 py-2 cursor-pointer hover:bg-[var(--accent)]"
                    >
                      <input
                        type="checkbox"
                        checked={keyEvidences.includes(ev.id)}
                        onChange={() => toggleEvidence(ev.id)}
                        className="accent-[var(--theme-primary)]"
                      />
                      <span className="text-sm">{ev.name}</span>
                    </label>
                  ))
                )}
              </div>
            </div>

            {/* 推理描述 */}
            <div className="mb-6">
              <label className="block text-xs font-bold text-[var(--muted-foreground)] mb-1.5">
                你的推理
              </label>
              <textarea
                value={deduction}
                onChange={(e) => setDeduction(e.target.value)}
                placeholder="描述你的推理过程……"
                rows={3}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--accent)] px-3 py-2 text-sm outline-none resize-none placeholder:text-[var(--muted-foreground)] focus:border-[var(--theme-primary)]"
              />
            </div>

            {/* 提交按钮 */}
            <button
              onClick={() => setShowConfirm(true)}
              disabled={!suspect || !motive || keyEvidences.length === 0}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-[var(--theme-primary)] py-3 font-bold transition-all hover:bg-[var(--theme-primary)]/80 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Send className="h-4 w-4" />
              提交推理
            </button>

            <p className="mt-2 text-center text-[10px] text-[var(--muted-foreground)]">
              ※ 提交后不可修改
            </p>
          </motion.div>
        </motion.div>
      )}

      {/* 提交中 */}
      {submitting && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/80"
        >
          <motion.div
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", damping: 15 }}
            className="text-center"
          >
            {/* 信封飞入 */}
            <motion.div
              animate={{ y: [50, 0], opacity: [0, 1] }}
              transition={{ duration: 0.5 }}
              className="mb-4"
            >
              <div className="mx-auto h-20 w-20 rounded-2xl bg-[var(--theme-primary)]/20 border border-[var(--theme-primary)]/30 flex items-center justify-center">
                <Send className="h-8 w-8 text-[var(--theme-primary)]" />
              </div>
            </motion.div>
            <p className="text-lg font-bold">正在提交你的推理…</p>
            <motion.div
              className="mt-4 mx-auto h-1 w-32 rounded-full bg-[var(--muted)] overflow-hidden"
            >
              <motion.div
                className="h-full rounded-full bg-[var(--theme-primary)]"
                animate={{ x: ["-100%", "200%"] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              />
            </motion.div>
          </motion.div>
        </motion.div>
      )}

      {/* 确认弹窗 */}
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
              onClick={(e) => e.stopPropagation()}
              className="relative max-w-sm w-full rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-6 text-center"
            >
              <AlertTriangle className="mx-auto h-10 w-10 text-[var(--warning)] mb-3" />
              <h3 className="text-lg font-bold mb-2">确认提交？</h3>
              <p className="text-sm text-[var(--muted-foreground)] mb-6">
                提交后不可修改，请确认你的推理
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
    </AnimatePresence>
  );
}
