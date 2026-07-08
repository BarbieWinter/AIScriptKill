/**
 * MediaController - 音频控制面板
 * 底部常驻，点击展开音量控制
 */

"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Volume2, VolumeX, Music, Mic, Speaker } from "lucide-react";

export function MediaController() {
  const [expanded, setExpanded] = useState(false);
  const [masterVol, setMasterVol] = useState(0.8);
  const [bgmVol, setBgmVol] = useState(0.6);
  const [voiceVol, setVoiceVol] = useState(0.7);
  const [sfxVol, setSfxVol] = useState(0.5);
  const [muted, setMuted] = useState(false);

  return (
    <div className="relative">
      {/* 触发按钮 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--accent)]/80 px-2.5 py-1.5 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
      >
        {muted ? (
          <VolumeX className="h-3.5 w-3.5" />
        ) : (
          <Volume2 className="h-3.5 w-3.5" />
        )}
        <span className="hidden sm:inline">BGM: 雪乡夜色</span>
      </button>

      {/* 展开控制面板 */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full right-0 mb-2 w-56 rounded-xl border border-[var(--border)] bg-[var(--panel-bg)] p-4 shadow-2xl backdrop-blur-xl"
          >
            {/* 总音量 */}
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                  <Volume2 className="h-3 w-3" />
                  总音量
                </span>
                <span className="text-xs text-[var(--muted-foreground)]">
                  {Math.round(masterVol * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={masterVol}
                onChange={(e) => {
                  setMasterVol(Number(e.target.value));
                  setMuted(Number(e.target.value) === 0);
                }}
                className="w-full accent-[var(--theme-primary)]"
              />
            </div>

            <div className="space-y-2">
              {/* BGM */}
              <div className="flex items-center gap-2">
                <Music className="h-3 w-3 text-[var(--muted-foreground)]" />
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={bgmVol}
                  onChange={(e) => setBgmVol(Number(e.target.value))}
                  className="flex-1 accent-[var(--theme-primary)]"
                />
                <span className="text-[10px] text-[var(--muted-foreground)] w-8 text-right">
                  {Math.round(bgmVol * 100)}%
                </span>
              </div>

              {/* 语音 */}
              <div className="flex items-center gap-2">
                <Mic className="h-3 w-3 text-[var(--muted-foreground)]" />
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={voiceVol}
                  onChange={(e) => setVoiceVol(Number(e.target.value))}
                  className="flex-1 accent-[var(--theme-primary)]"
                />
                <span className="text-[10px] text-[var(--muted-foreground)] w-8 text-right">
                  {Math.round(voiceVol * 100)}%
                </span>
              </div>

              {/* 音效 */}
              <div className="flex items-center gap-2">
                <Speaker className="h-3 w-3 text-[var(--muted-foreground)]" />
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={sfxVol}
                  onChange={(e) => setSfxVol(Number(e.target.value))}
                  className="flex-1 accent-[var(--theme-primary)]"
                />
                <span className="text-[10px] text-[var(--muted-foreground)] w-8 text-right">
                  {Math.round(sfxVol * 100)}%
                </span>
              </div>
            </div>

            {/* 当前曲目 */}
            <div className="mt-3 pt-3 border-t border-[var(--border)]">
              <p className="text-[10px] text-[var(--muted-foreground)]">
                正在播放: 雪乡夜色
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
