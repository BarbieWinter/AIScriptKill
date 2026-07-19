/**
 * EvidenceBackpack - 证物背包面板
 * 展示已发现证物，支持出示证物操作
 */

"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sheet } from "@/components/ui/Sheet";
import { useActiveGameStore } from "@/components/game/GameSessionBoundary";
import { Eye, Share2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { AvailableCharacter, Evidence } from "@/lib/game/types";
import { toast } from "sonner";

interface EvidenceBackpackProps {
  open?: boolean;
  onClose?: () => void;
  sessionId?: string | null;
  playerCharacterId?: string | null;
  evidences?: Evidence[];
  characters?: AvailableCharacter[];
  onViewEvidence?: (evidenceId: string) => Promise<{ evidence_id: string; status: string }>;
  onShowEvidence?: (characterId: string, evidenceId: string) => Promise<unknown>;
}

export function EvidenceBackpack({
  open: controlledOpen,
  onClose: controlledOnClose,
  sessionId: controlledSessionId,
  playerCharacterId: controlledPlayerCharacterId,
  evidences: controlledEvidences,
  characters: controlledCharacters,
  onViewEvidence,
  onShowEvidence,
}: EvidenceBackpackProps = {}) {
  const storeOpen = useActiveGameStore((s) => s.activePanel === "evidence");
  const storeSessionId = useActiveGameStore((s) => s.sessionId);
  const storePlayerCharacterId = useActiveGameStore((s) => s.playerCharacterId);
  const storeEvidences = useActiveGameStore((s) => s.discoveredEvidences);
  const storeCharacters = useActiveGameStore((s) => s.availableCharacters);
  const closePanel = useActiveGameStore((s) => s.closePanel);
  const open = controlledOpen ?? storeOpen;
  const onClose = controlledOnClose ?? closePanel;
  const sessionId = controlledSessionId ?? storeSessionId;
  const playerCharacterId = controlledPlayerCharacterId ?? storePlayerCharacterId;
  const evidences = controlledEvidences ?? storeEvidences;
  const characters = controlledCharacters ?? storeCharacters;
  const updateEvidence = useActiveGameStore((s) => s.updateEvidence);

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showNpcList, setShowNpcList] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const selected = evidences[selectedIndex];
  const selectedImageUrl = selected?.image_url;
  const characterList = characters.filter(
    (character) => character.id !== playerCharacterId,
  );

  useEffect(() => {
    if (selectedIndex >= evidences.length) setSelectedIndex(0);
  }, [evidences.length, selectedIndex]);

  useEffect(() => {
    if (!open || !sessionId || !selected || selected.status === "viewed") return;

    let cancelled = false;
    const markViewed = async () => {
      try {
        const result = onViewEvidence
          ? await onViewEvidence(selected.id)
          : await api.viewEvidence(sessionId, selected.id);
        if (!cancelled && !onViewEvidence) {
          updateEvidence(selected.id, { status: result.status });
        }
      } catch (error) {
        console.error("[EvidenceBackpack] 标记证物已查看失败:", error);
      }
    };
    void markViewed();
    return () => {
      cancelled = true;
    };
  }, [onViewEvidence, open, selected, sessionId, updateEvidence]);

  /** 出示证物给角色 */
  const handleShowEvidence = async (charId: string) => {
    if (!sessionId || !selected || submitting) return;
    setSubmitting(true);
    try {
      const result = onShowEvidence
        ? await onShowEvidence(charId, selected.id)
        : await api.performAction(sessionId, "show_evidence", {
            character_id: charId,
            evidence_id: selected.id,
          });

      const characterName = characterList.find((character) => character.id === charId)?.name ?? charId;
      const reaction = result as { text?: string };
      toast.success("证物已出示", {
        description: reaction.text ?? `你向${characterName}出示了「${selected.name}」。`,
      });

      if (!onShowEvidence) {
        const shown = Array.from(new Set([...(selected.shown_to_characters ?? []), charId]));
        updateEvidence(selected.id, { shown_to_characters: shown });
      }
      setShowNpcList(false);
    } catch (error) {
      console.error("[EvidenceBackpack] 出示证物失败:", error);
      toast.error("当前无法出示这件证物");
    } finally {
      setSubmitting(false);
    }
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
                {/* 证物图片 */}
                <div className="aspect-[4/3] bg-gradient-to-br from-[var(--theme-primary)]/20 to-[var(--theme-accent)]/10 flex items-center justify-center overflow-hidden">
                  {selectedImageUrl && !selectedImageUrl.startsWith("storage://") ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={selectedImageUrl}
                      alt={selected.name}
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <Eye className="h-12 w-12 text-[var(--muted-foreground)]/30" />
                  )}
                </div>

                {/* 证物信息 */}
                <div className="p-4">
                  <h3 className="text-lg font-bold mb-1">{selected?.name}</h3>
                  <p className="text-sm text-[var(--muted-foreground)] leading-relaxed">
                    {selected?.description ?? selected?.description_surface}
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
              disabled={submitting || selected?.can_show_to_npc === false}
              className="flex items-center gap-1.5 rounded-lg bg-[var(--theme-primary)] px-4 py-2 text-xs font-bold transition-colors hover:bg-[var(--theme-primary)]/80 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Share2 className="h-3.5 w-3.5" />
              {submitting ? "出示中…" : "出示"}
            </button>
          </div>

          {/* NPC 选择列表弹窗 */}
          {showNpcList && (
            <div className="px-4 pb-3">
              <p className="text-xs text-[var(--muted-foreground)] mb-2">选择出示对象：</p>
              <div className="flex flex-wrap gap-2">
                {characterList.length === 0 ? (
                  <p className="text-xs text-[var(--muted-foreground)]">当前场景没有可出示对象</p>
                ) : (
                  characterList.map((char) => (
                    <button
                      key={char.id}
                      onClick={() => void handleShowEvidence(char.id)}
                      disabled={submitting}
                      className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs transition-colors hover:border-[var(--theme-primary)] hover:bg-[var(--accent)] disabled:opacity-40"
                    >
                      {char.name}
                    </button>
                  ))
                )}
              </div>
            </div>
          )}

          {/* 证物缩略图列表 */}
          <div className="px-4 pb-4">
            <p className="text-xs text-[var(--muted-foreground)] mb-2">证物列表：</p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {evidences.map((ev, idx) => (
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
