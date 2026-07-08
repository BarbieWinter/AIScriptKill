/**
 * EvidenceBackpack - 证物背包面板
 * 展示已发现证物，支持出示证物操作
 */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sheet } from "@/components/ui/Sheet";
import { useGameStore } from "@/stores/gameStore";
import { Eye, Share2, Crosshair } from "lucide-react";
import { cn } from "@/lib/utils";
import { getMockEngine } from "@/lib/mock-data";
import { toast } from "sonner";

// 角色列表（用于出示证物）
const characterList = [
  { id: "wangdada", name: "王大达" },
  { id: "chengjun", name: "程俊" },
];

export function EvidenceBackpack() {
  const open = useGameStore((s) => s.activePanel === "evidence");
  const onClose = () => useGameStore.getState().closePanel();
  const evidences = useGameStore((s) => s.discoveredEvidences);
  const addMessage = useGameStore((s) => s.addMessage);

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showNpcList, setShowNpcList] = useState(false);

  const selected = evidences[selectedIndex];

  /** 出示证物给角色 */
  const handleShowEvidence = (charId: string) => {
    if (!selected) return;
    const engine = getMockEngine();
    const result = engine.showEvidence(charId, selected.id);

    // 添加 DM 叙述
    addMessage({
      id: `msg-ev-${Date.now()}`,
      role: "npc",
      character_id: "dm",
      text: `你向${characterList.find((c) => c.id === charId)?.name}出示了「${selected.name}」。`,
      emotion: "calm",
      timestamp: new Date().toISOString(),
    });

    // 添加 NPC 反应
    addMessage({
      id: `msg-ev-${Date.now() + 1}`,
      role: "npc",
      character_id: charId,
      text: result.text,
      emotion: result.emotion,
      timestamp: new Date().toISOString(),
    });

    setShowNpcList(false);
    toast.success("证物已出示");
  };

  return (
    <Sheet open={open} onClose={onClose} title="证物背包">
      {evidences.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-sm text-[var(--muted-foreground)]">
          <p className="mb-2">🎒 背包空空如也</p>
          <p className="text-xs">调查场景热点可能发现证物</p>
        </div>
      ) : (
        <>
          {/* 选中证物大图 */}
          <div className="px-4 pt-3">
            <AnimatePresence mode="wait">
              <motion.div
                key={selected?.id}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="rounded-xl border border-[var(--border)] overflow-hidden"
              >
                {/* 证物图片占位 */}
                <div className="aspect-[4/3] bg-gradient-to-br from-[var(--theme-primary)]/20 to-[var(--theme-accent)]/10 flex items-center justify-center">
                  <Eye className="h-12 w-12 text-[var(--muted-foreground)]/30" />
                </div>

                {/* 证物信息 */}
                <div className="p-4">
                  <h3 className="text-lg font-bold mb-1">{selected?.name}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-relaxed">
                    {selected?.description_surface}
                  </p>

                  {/* 状态 */}
                  <div className="mt-3 flex items-center gap-2 text-xs">
                    <span className="rounded-full bg-[var(--success)]/10 px-2 py-0.5 text-[var(--success)]">
                      已调查
                    </span>
                    {selected?.shown_to_characters?.length > 0 && (
                      <span className="rounded-full bg-[var(--theme-primary)]/10 px-2 py-0.5 text-[var(--theme-primary)]">
                        已出示给 {selected.shown_to_characters.length} 人
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>

          {/* 操作按钮 */}
          <div className="flex gap-2 px-4 py-3">
            <button
              onClick={() => setShowNpcList(true)}
              className="flex items-center gap-1.5 rounded-lg bg-[var(--theme-primary)] px-4 py-2 text-xs font-bold transition-colors hover:bg-[var(--theme-primary)]/80"
            >
              <Share2 className="h-3.5 w-3.5" />
              出示
            </button>
            <button className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-4 py-2 text-xs transition-colors hover:bg-[var(--accent)]">
              <Crosshair className="h-3.5 w-3.5" />
              用于推理
            </button>
          </div>

          {/* NPC 选择列表弹窗 */}
          {showNpcList && (
            <div className="px-4 pb-3">
              <p className="text-xs text-[var(--muted-foreground)] mb-2">选择出示对象：</p>
              <div className="flex gap-2">
                {characterList.map((char) => (
                  <button
                    key={char.id}
                    onClick={() => handleShowEvidence(char.id)}
                    className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs transition-colors hover:border-[var(--theme-primary)] hover:bg-[var(--accent)]"
                  >
                    {char.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 证物缩略图列表 */}
          <div className="px-4 pb-4">
            <p className="text-xs text-[var(--muted-foreground)] mb-2">证物列表：</p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {evidences.map((ev: any, idx: number) => (
                <button
                  key={ev.id}
                  onClick={() => setSelectedIndex(idx)}
                  className={cn(
                    "flex-shrink-0 rounded-lg border-2 p-2 transition-all",
                    idx === selectedIndex
                      ? "border-[var(--theme-primary)] bg-[var(--theme-primary)]/10"
                      : "border-[var(--border)] bg-[var(--accent)] hover:border-[var(--muted-foreground)]"
                  )}
                >
                  <div className="h-12 w-12 rounded-md bg-gradient-to-br from-[var(--theme-primary)]/20 to-[var(--theme-accent)]/10 flex items-center justify-center">
                    <span className="text-[10px] text-[var(--muted-foreground)]">
                      {ev.name.slice(0, 2)}
                    </span>
                  </div>
                  <p className="mt-1 text-[10px] text-center text-[var(--muted-foreground)] w-12 truncate">
                    {ev.name}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </Sheet>
  );
}
