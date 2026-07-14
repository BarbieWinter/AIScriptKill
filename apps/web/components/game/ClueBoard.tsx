/**
 * ClueBoard - 线索板面板
 * 桌面端: Sheet 从右侧滑出
 * 手机端: Drawer 从底部弹出
 * 展示已解锁线索卡片瀑布流
 */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sheet } from "@/components/ui/Sheet";
import { useGameStore } from "@/stores/gameStore";
import {
  Search,
  Star,
  Filter,
} from "lucide-react";
import { cn } from "@/lib/utils";

export function ClueBoard() {
  const open = useGameStore((s) => s.activePanel === "clue");
  const onClose = () => useGameStore.getState().closePanel();
  const clues = useGameStore((s) => s.unlockedClues);
  const totalCluesInRound = useGameStore((s) => s.totalCluesInRound);
  const [filter, setFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedClue, setSelectedClue] = useState<any>(null);

  // 过滤线索
  const filteredClues = clues.filter((clue: any) => {
    if (filter === "key" && !clue.is_key) return false;
    if (filter === "normal" && clue.is_key) return false;
    if (searchQuery && !clue.name.includes(searchQuery) && !clue.description.includes(searchQuery)) return false;
    return true;
  });

  return (
    <>
      <Sheet open={open} onClose={onClose} title="线索板">
        {/* 搜索栏 */}
        <div className="px-4 pt-3 pb-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <input
              type="text"
              placeholder="搜索线索…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--accent)] py-2 pl-10 pr-4 text-sm outline-none placeholder:text-[var(--muted-foreground)] focus:border-[var(--theme-primary)]"
            />
          </div>
        </div>

        {/* 筛选标签 */}
        <div className="flex gap-2 px-4 pb-3 overflow-x-auto">
          {[
            { id: "all", label: "全部" },
            { id: "key", label: "★ 关键" },
            { id: "normal", label: "普通" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className={cn(
                "whitespace-nowrap rounded-full px-3 py-1 text-xs transition-colors",
                filter === tab.id
                  ? "bg-[var(--theme-primary)] text-white"
                  : "border border-[var(--border)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 线索进度 */}
        <div className="px-4 pb-3">
          <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)] mb-1">
            <span>线索进度</span>
            <span>{clues.length} 已发现</span>
          </div>
          <div className="h-1.5 rounded-full bg-[var(--muted)] overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-[var(--theme-primary)]"
              initial={{ width: 0 }}
              animate={{
                width: `${Math.min(
                  100,
                  (clues.length / Math.max(totalCluesInRound, 1)) * 100
                )}%`,
              }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            />
          </div>
        </div>

        {/* 线索卡片列表 */}
        <div className="px-4 pb-4 space-y-3">
          {filteredClues.length === 0 ? (
            <div className="py-8 text-center text-sm text-[var(--muted-foreground)]">
              {clues.length === 0 ? (
                <>
                  <p className="mb-2">🔍 还没有发现任何线索</p>
                  <p className="text-xs">试试调查场景中的热点区域</p>
                </>
              ) : (
                <p>没有匹配的线索</p>
              )}
            </div>
          ) : (
            <motion.div
              initial="hidden"
              animate="show"
              variants={{
                hidden: {},
                show: { transition: { staggerChildren: 0.06 } },
              }}
              className="grid grid-cols-2 gap-3"
            >
              {filteredClues.map((clue: any) => (
                <motion.button
                  key={clue.id}
                  variants={{
                    hidden: { opacity: 0, y: 15 },
                    show: { opacity: 1, y: 0 },
                  }}
                  onClick={() => setSelectedClue(clue)}
                  className={cn(
                    "group rounded-xl border p-3 text-left transition-all",
                    clue.is_key
                      ? "border-[var(--warning)]/30 bg-[var(--warning)]/5"
                      : "border-[var(--border)] bg-[var(--accent)]",
                    "hover:border-[var(--theme-primary)]"
                  )}
                >
                  {/* 缩略图 */}
                  <div
                    className={cn(
                      "mb-2 aspect-[4/3] rounded-lg bg-gradient-to-br",
                      clue.is_key
                        ? "from-[var(--warning)]/20 to-[var(--warning)]/5"
                        : "from-[var(--theme-primary)]/10 to-transparent"
                    )}
                  />
                  <div className="flex items-start justify-between gap-1">
                    <p className="text-xs font-medium line-clamp-2">{clue.name}</p>
                    {clue.is_key && (
                      <Star className="h-3 w-3 flex-shrink-0 fill-[var(--warning)] text-[var(--warning)]" />
                    )}
                  </div>
                </motion.button>
              ))}
            </motion.div>
          )}
        </div>
      </Sheet>

      {/* 线索详情 Dialog */}
      <AnimatePresence>
        {selectedClue && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[70] flex items-center justify-center p-4"
            onClick={() => setSelectedClue(null)}
          >
            {/* 遮罩 */}
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

            {/* 卡片 */}
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ type: "spring", damping: 20 }}
              onClick={(e) => e.stopPropagation()}
              className={cn(
                "relative max-w-md w-full rounded-2xl border p-6",
                selectedClue.is_key
                  ? "border-[var(--warning)]/30 bg-gradient-to-b from-[var(--warning)]/5 to-[var(--background)]"
                  : "border-[var(--border)] bg-[var(--panel-bg)]"
              )}
            >
              {/* 线索大图 */}
              <div
                className={cn(
                  "mb-4 aspect-[16/9] rounded-xl bg-gradient-to-br",
                  selectedClue.is_key
                    ? "from-[var(--warning)]/30 to-[var(--warning)]/10"
                    : "from-[var(--theme-primary)]/20 to-transparent"
                )}
              />
              <div className="flex items-center gap-2 mb-3">
                <h3 className="text-lg font-bold">{selectedClue.name}</h3>
                {selectedClue.is_key && (
                  <span className="rounded-full bg-[var(--warning)]/20 px-2 py-0.5 text-[10px] text-[var(--warning)]">
                    关键线索
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
                {selectedClue.description}
              </p>
              <button
                onClick={() => setSelectedClue(null)}
                className="mt-6 w-full rounded-lg bg-[var(--accent)] py-2 text-sm transition-colors hover:bg-[var(--muted)]"
              >
                关闭
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
