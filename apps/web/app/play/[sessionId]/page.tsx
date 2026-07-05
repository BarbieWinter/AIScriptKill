"use client";

import { useParams } from "next/navigation";

export default function GamePage() {
  const params = useParams();
  const sessionId = params.sessionId as string;

  return (
    <main className="relative h-screen w-full overflow-hidden bg-[var(--background)]">
      {/* Layer 1: 场景背景 */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#1a1a2e] to-[#0a0a0b]" />

      {/* Layer 2: 场景热区层 (Konva) */}
      <div className="absolute inset-0" />

      {/* Layer 3: 顶部操作栏 */}
      <header className="absolute left-0 right-0 top-0 z-30 border-b border-[var(--border)]/50 bg-[var(--background)]/60 backdrop-blur-md">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--muted-foreground)]">雪乡村口</span>
          </div>
          <div className="flex items-center gap-3">
            <button className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--accent)]">
              线索板
            </button>
            <button className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--accent)]">
              背包
            </button>
            <button className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--accent)]">
              笔记
            </button>
          </div>
        </div>
      </header>

      {/* Layer 4: 底部对话/叙事区 */}
      <div className="absolute bottom-0 left-0 right-0 z-20 border-t border-[var(--border)]/50 bg-[var(--background)]/80 backdrop-blur-md">
        <div className="mx-auto max-w-4xl">
          {/* 对话历史 */}
          <div className="max-h-48 overflow-y-auto px-4 py-3">
            <p className="dm-narration mb-3 text-sm">夜幕降临，雪乡的灯笼亮了起来。</p>
            <div className="mb-3 flex items-start gap-3">
              <div className="mt-1 h-8 w-8 flex-shrink-0 rounded-full bg-gradient-to-br from-purple-500/50 to-pink-500/50" />
              <div>
                <p className="mb-1 text-sm font-bold">王大达</p>
                <p className="text-sm text-[var(--muted-foreground)]">
                  "你们可算来了！我都等半天了。快进来坐，外面冷！"
                </p>
              </div>
            </div>
          </div>

          {/* 输入区 */}
          <div className="border-t border-[var(--border)]/50 px-4 py-3">
            <div className="flex gap-3">
              <input
                type="text"
                placeholder="输入你的问题… @角色名 或 /dm"
                className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--accent)] px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-[var(--muted-foreground)] focus:border-[var(--theme-primary)]"
              />
              <button className="rounded-lg bg-[var(--theme-primary)] px-6 py-2.5 text-sm font-bold transition-colors hover:bg-[var(--theme-primary)]/80">
                发送
              </button>
            </div>
            <div className="mt-2 flex gap-3 text-xs text-[var(--muted-foreground)]">
              <span className="cursor-pointer hover:text-[var(--foreground)]">@王大达</span>
              <span className="cursor-pointer hover:text-[var(--foreground)]">@dm</span>
              <span className="cursor-pointer hover:text-[var(--foreground)]">[出示证物]</span>
            </div>
          </div>
        </div>
      </div>

      {/* Layer 5: 底部状态栏 */}
      <div className="absolute bottom-0 left-0 right-0 z-10 px-4 py-1 text-center text-xs text-[var(--muted-foreground)]">
        ♪ 雪乡夜色  ·  00:12:34
      </div>
    </main>
  );
}
