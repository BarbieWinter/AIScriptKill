/**
 * SceneHotspots — 场景交互热区
 *
 * 让玩家感觉"在调查现场"，不是"在点击按钮"。
 * - 悬停时发光 + 脉冲
 * - 点击时涟漪扩散
 * - 发现物品时有飞出动画
 */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { getMockEngine } from "@/lib/mock-data";
import { useGameStore } from "@/stores/gameStore";
import { Search } from "lucide-react";

interface Hotspot {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface SceneHotspotsProps {
  sceneId: string;
  hotspots: Hotspot[];
}

export function SceneHotspots({ sceneId, hotspots }: SceneHotspotsProps) {
  const addMessage = useGameStore((s) => s.addMessage);
  const addClue = useGameStore((s) => s.addClue);
  const addEvidence = useGameStore((s) => s.addEvidence);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [discoveredIds, setDiscoveredIds] = useState<Set<string>>(new Set());

  const handleClick = (hotspot: Hotspot) => {
    if (discoveredIds.has(hotspot.id)) return;
    setActiveId(hotspot.id);

    const engine = getMockEngine();
    const result = engine.examineScene(sceneId, hotspot.id);

    addMessage({
      id: `scene-${Date.now()}`,
      role: "npc",
      character_id: "dm",
      text: result.dm_narration,
      emotion: "calm",
      timestamp: new Date().toISOString(),
    });

    const hasContent = result.discovered_clues?.length > 0 || result.discovered_evidences?.length > 0;
    if (hasContent) {
      setDiscoveredIds((prev) => new Set(prev).add(hotspot.id));
    }

    result.discovered_clues?.forEach((clue: any, i: number) => {
      setTimeout(() => addClue(clue), 400 + i * 200);
    });
    result.discovered_evidences?.forEach((ev: any, i: number) => {
      setTimeout(() => addEvidence(ev), 600 + i * 200);
    });

    setTimeout(() => setActiveId(null), 800);
  };

  return (
    <div className="absolute inset-0 z-20 pointer-events-none">
      {/* 提示文字（无发现过的热区时显示） */}
      {hotspots.filter((h) => !discoveredIds.has(h.id)).length > 0 && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-30">
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.5, 0] }}
            transition={{ duration: 3, repeat: Infinity, repeatDelay: 2 }}
            className="text-[10px] text-white/30 tracking-widest whitespace-nowrap"
          >
            调查场景中的可疑之处
          </motion.p>
        </div>
      )}

      {hotspots.map((hotspot) => {
        const isDiscovered = discoveredIds.has(hotspot.id);

        return (
          <div
            key={hotspot.id}
            className="pointer-events-auto absolute"
            style={{
              left: `${hotspot.x}%`,
              top: `${hotspot.y}%`,
              width: `${hotspot.width}%`,
              height: `${hotspot.height}%`,
              minWidth: "48px",
              minHeight: "48px",
            }}
          >
            <button
              onClick={() => handleClick(hotspot)}
              disabled={isDiscovered}
              className="group relative w-full h-full flex items-center justify-center"
            >
              {/* 热区背景 */}
              <motion.div
                whileHover={!isDiscovered ? { scale: 1.05 } : {}}
                whileTap={!isDiscovered ? { scale: 0.95 } : {}}
                animate={
                  activeId === hotspot.id
                    ? { scale: [1, 1.2, 1], opacity: [1, 0.5, 1] }
                    : {}
                }
                className={`absolute inset-0 rounded-lg border-2 transition-all duration-300 ${
                  isDiscovered
                    ? "border-white/5 bg-white/[0.02]"
                    : "border-white/10 bg-white/[0.03] group-hover:border-[var(--theme-primary)]/50 group-hover:bg-[var(--theme-primary)]/10 group-hover:shadow-[0_0_20px_rgba(124,58,237,0.2)]"
                }`}
              />

              {/* 标签 */}
              <motion.span
                initial={{ opacity: 0.6 }}
                whileHover={{ opacity: 1 }}
                className={`relative z-10 flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] backdrop-blur-sm transition-all ${
                  isDiscovered
                    ? "bg-black/20 text-white/20"
                    : "bg-black/50 text-white/70 group-hover:bg-[var(--theme-primary)]/60 group-hover:text-white group-hover:shadow-lg"
                }`}
              >
                {isDiscovered ? (
                  <>✓ 已查看</>
                ) : (
                  <>
                    <Search className="h-3 w-3" />
                    <span className="hidden sm:inline">{hotspot.label.replace("🔍 ", "")}</span>
                    <span className="sm:hidden">查看</span>
                  </>
                )}
              </motion.span>

              {/* 脉冲环（仅未发现时） */}
              {!isDiscovered && (
                <div
                  className="absolute inset-0 rounded-lg"
                  style={{
                    animation: "pulse-ring 3s ease-in-out infinite",
                    border: "1px solid rgba(124,58,237,0.1)",
                  }}
                />
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
}
