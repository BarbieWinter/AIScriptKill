/**
 * CharacterChapters — 当前玩家角色已授权的人物剧本章节
 */

"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { BookOpen, Check } from "lucide-react";
import { toast } from "sonner";

import { Sheet } from "@/components/ui/Sheet";
import { api } from "@/lib/api";
import { useGameStore } from "@/stores/gameStore";

interface ChapterSummary {
  id: string;
  character_id: string;
  order: number;
  title: string;
  status: string;
}

interface ChapterContent extends ChapterSummary {
  content: string;
}

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={index} className="font-semibold text-[var(--foreground)]">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        )
      )}
    </>
  );
}

function ChapterArticle({ content }: { content: string }) {
  const blocks = content.trim().split(/\n\s*\n/);
  return (
    <div className="space-y-5 text-[15px] leading-8 text-[var(--foreground)]/85">
      {blocks.map((block, index) => {
        const quote = block.match(/^>\s?(.*)$/s);
        if (quote) {
          return (
            <blockquote
              key={index}
              className="rounded-r-lg border-l-2 border-[var(--theme-primary)] bg-[var(--theme-primary)]/8 px-4 py-3 italic text-[var(--foreground)]/75"
            >
              <InlineMarkdown text={quote[1]} />
            </blockquote>
          );
        }
        return (
          <p key={index} className="whitespace-pre-wrap">
            <InlineMarkdown text={block} />
          </p>
        );
      })}
    </div>
  );
}

export function CharacterChapters() {
  const open = useGameStore((state) => state.activePanel === "chapter");
  const sessionId = useGameStore((state) => state.sessionId);
  const [chapters, setChapters] = useState<ChapterSummary[]>([]);
  const [selected, setSelected] = useState<ChapterContent | null>(null);
  const [loading, setLoading] = useState(false);

  const loadChapters = useCallback(async () => {
    if (!sessionId) return;
    try {
      const result = await api.getCharacterChapters(sessionId);
      setChapters(result.chapters);
      setSelected((current) => {
        if (!current) return null;
        const latest = result.chapters.find((chapter) => chapter.id === current.id);
        return latest ? { ...current, status: latest.status } : null;
      });
    } catch (error) {
      console.error("[CharacterChapters] 加载章节目录失败:", error);
      toast.error("无法加载人物章节");
    }
  }, [sessionId]);

  useEffect(() => {
    if (open) void loadChapters();
  }, [loadChapters, open]);

  const readChapter = async (chapterId: string) => {
    if (!sessionId || loading) return;
    setLoading(true);
    try {
      const chapter = await api.readCharacterChapter(sessionId, chapterId);
      setSelected(chapter);
      await loadChapters();
    } catch (error) {
      console.error("[CharacterChapters] 读取章节失败:", error);
      toast.error("章节暂时无法打开");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={() => useGameStore.getState().closePanel()}
      title="卓司元的人物章节"
      className="md:w-[min(760px,72vw)]"
    >
      <div className="grid h-full min-h-0 grid-cols-1 md:grid-cols-[200px_minmax(0,1fr)]">
        <div className="shrink-0 border-b border-[var(--border)] p-3 md:overflow-y-auto md:border-b-0 md:border-r">
          {chapters.length === 0 ? (
            <p className="py-8 text-center text-xs text-[var(--muted-foreground)]">
              当前没有已授权章节
            </p>
          ) : (
            <div className="space-y-2">
              {chapters.map((chapter) => (
                <button
                  key={chapter.id}
                  onClick={() => void readChapter(chapter.id)}
                  disabled={loading}
                  className={`flex w-full items-start gap-2 rounded-lg border p-3 text-left text-xs transition-colors ${
                    selected?.id === chapter.id
                      ? "border-[var(--theme-primary)] bg-[var(--theme-primary)]/10"
                      : "border-[var(--border)] hover:bg-[var(--accent)]"
                  }`}
                >
                  {chapter.status === "viewed" ? (
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--success)]" />
                  ) : (
                    <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  )}
                  <span>
                    <span className="block text-[10px] text-[var(--muted-foreground)]">
                      第 {chapter.order} 章
                    </span>
                    <span className="mt-0.5 block font-medium">{chapter.title}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <article className="min-h-0 overflow-y-auto px-5 py-6 md:px-8 md:py-8">
          {selected ? (
            <>
              <div className="mb-5 border-b border-[var(--border)] pb-4">
                <p className="text-xs text-[var(--muted-foreground)]">
                  第 {selected.order} 章 · {selected.status === "viewed" ? "已读" : "已授权"}
                </p>
                <h3 className="mt-1 text-xl font-bold">{selected.title}</h3>
              </div>
              <ChapterArticle content={selected.content} />
            </>
          ) : (
            <div className="flex min-h-64 flex-col items-center justify-center text-center text-[var(--muted-foreground)]">
              <BookOpen className="mb-3 h-8 w-8 opacity-40" />
              <p className="text-sm">选择已授权章节开始阅读</p>
              <p className="mt-1 text-xs">阅读进度会影响后续章节与阶段推进。</p>
            </div>
          )}
        </article>
      </div>
    </Sheet>
  );
}
