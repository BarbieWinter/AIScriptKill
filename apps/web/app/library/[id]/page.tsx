"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { mockCharacters } from "@/lib/mock-data";
import {
  ChevronLeft,
  Clock,
  Star,
  Play,
  User,
  Quote,
  Headphones,
} from "lucide-react";

const pageTransition = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: "easeInOut" },
};

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
};
const itemVariants = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0 },
};

export default function ScriptDetailPage() {
  const params = useParams();
  const router = useRouter();
  const scriptId = params.id as string;

  const [pkg, setPkg] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedChar, setSelectedChar] = useState<any>(null);

  const playableCharacters = mockCharacters.filter((c) => c.playable);

  useEffect(() => {
    let isCurrent = true;

    setLoading(true);
    setLoadError(null);
    setPkg(null);

    api
      .getPackage(scriptId)
      .then((data) => {
        if (!isCurrent) {
          return;
        }
        setPkg(data);
      })
      .catch(() => {
        if (!isCurrent) {
          return;
        }
        setLoadError("剧本加载失败，请确认后端服务已启动，或使用 Mock 模式浏览。");
      })
      .finally(() => {
        if (!isCurrent) {
          return;
        }
        setLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [scriptId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-[var(--theme-primary)] border-t-transparent animate-spin mb-4" />
          <p className="text-sm text-[var(--muted-foreground)]">加载中…</p>
        </div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="min-h-screen bg-[var(--background)] flex items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <p className="text-lg font-bold mb-2">剧本加载失败</p>
          <p className="text-sm leading-relaxed text-[var(--muted-foreground)] mb-5">
            {loadError}
          </p>
          <button
            onClick={() => router.push("/library")}
            className="text-sm text-[var(--theme-primary)] hover:underline"
          >
            返回剧本库
          </button>
        </div>
      </main>
    );
  }

  if (!pkg) {
    return (
      <main className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg text-[var(--muted-foreground)] mb-4">剧本未找到</p>
          <button
            onClick={() => router.push("/library")}
            className="text-sm text-[var(--theme-primary)] hover:underline"
          >
            返回剧本库
          </button>
        </div>
      </main>
    );
  }

  return (
    <motion.main {...pageTransition} className="min-h-screen bg-[var(--background)]">
      <div className="mx-auto max-w-4xl px-4 md:px-6 py-6 pb-24 md:pb-12">
        {/* 返回 */}
        <button
          onClick={() => router.back()}
          className="mb-6 inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
        >
          <ChevronLeft className="h-4 w-4" />
          返回
        </button>

        {/* 宣传视频区 */}
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="relative mb-8 aspect-video rounded-2xl overflow-hidden bg-gradient-to-br from-[var(--theme-primary)]/30 to-[var(--theme-secondary)] border border-[var(--border)]"
        >
          <div className="absolute inset-0 flex items-center justify-center">
            <button className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--theme-primary)]/80 transition-transform hover:scale-105">
              <Play className="h-6 w-6 ml-1" />
            </button>
          </div>
          <div className="absolute bottom-3 left-3 rounded-lg bg-black/60 px-2.5 py-1 text-xs text-white/80 backdrop-blur-sm">
            宣传片 · 01:30
          </div>
        </motion.div>

        {/* 标题信息区 */}
        <section className="mb-8">
          <h1 className="text-3xl md:text-4xl font-bold mb-3">{pkg.title}</h1>
          <div className="flex flex-wrap items-center gap-3 md:gap-4 text-sm text-[var(--muted-foreground)] mb-4">
            <div className="flex items-center gap-1">
              <Star className="h-4 w-4 fill-[var(--warning)] text-[var(--warning)]" />
              <span>{pkg.difficulty}/5 难度</span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="h-4 w-4" />
              <span>约 {pkg.duration_minutes} 分钟</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {pkg.genre?.map((g: string) => (
              <span
                key={g}
                className="rounded-full border border-[var(--border)] px-3 py-1 text-xs text-[var(--muted-foreground)]"
              >
                {g}
              </span>
            ))}
          </div>
        </section>

        {/* 故事简介 */}
        <section className="mb-8">
          <h2 className="text-lg font-bold mb-3">故事简介</h2>
          <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
            {pkg.description}
          </p>
        </section>

        {/* 角色预览 */}
        <section className="mb-8">
          <h2 className="text-lg font-bold mb-4">角色预览</h2>
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="show"
            className="grid grid-cols-3 md:grid-cols-6 gap-3"
          >
            {playableCharacters.map((char) => (
              <motion.button
                key={char.id}
                variants={itemVariants}
                whileHover={{ y: -4 }}
                onClick={() => setSelectedChar(char)}
                className="group flex flex-col items-center rounded-xl border border-[var(--border)] p-3 md:p-4 transition-all hover:border-[var(--theme-primary)] hover:shadow-lg hover:shadow-[var(--theme-primary)]/10"
              >
                <div className="mb-2 h-16 w-16 md:h-20 md:w-20 rounded-full bg-gradient-to-br from-[var(--theme-primary)]/30 to-[var(--theme-accent)]/30 flex items-center justify-center transition-transform group-hover:scale-105">
                  <User className="h-8 w-8 text-white/30" />
                </div>
                <p className="text-xs md:text-sm font-bold">{char.name}</p>
                <p className="text-[10px] text-[var(--muted-foreground)] mt-0.5">
                  {char.personality?.split("、")[0]}
                </p>
              </motion.button>
            ))}
          </motion.div>
        </section>

        {/* 沉浸提示 */}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--accent)] p-4 flex items-start gap-3">
          <Headphones className="h-5 w-5 text-[var(--theme-primary)] flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-bold mb-1">沉浸体验提示</p>
            <p className="text-xs text-[var(--muted-foreground)]">
              本游戏建议在安静环境中体验，推荐佩戴耳机以获得最佳沉浸效果。
            </p>
          </div>
        </div>

        {/* CTA 按钮 (桌面: 固定底部, 手机: sticky) */}
        <div className="fixed bottom-0 left-0 right-0 md:static md:mt-8 z-20 border-t border-[var(--border)] bg-[var(--background)]/95 backdrop-blur-sm md:bg-transparent md:border-0 md:backdrop-blur-none">
          <div className="max-w-4xl mx-auto px-4 md:px-0 py-3 md:py-0">
            <button
              onClick={() => router.push(`/play/${scriptId}/select`)}
              className="w-full md:w-auto rounded-xl bg-[var(--theme-primary)] px-8 md:px-12 py-3.5 md:py-4 text-base font-bold transition-all hover:bg-[var(--theme-primary)]/80 hover:shadow-lg hover:shadow-[var(--theme-primary)]/30"
            >
              开始游戏
            </button>
          </div>
        </div>
      </div>

      {/* 角色详情 Dialog */}
      <AnimatePresence>
        {selectedChar && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={() => setSelectedChar(null)}
          >
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
            <motion.div
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 20 }}
              transition={{ type: "spring", damping: 20 }}
              onClick={(e) => e.stopPropagation()}
              className="relative max-w-sm w-full rounded-2xl border border-[var(--border)] bg-[var(--panel-bg)] p-6"
            >
              {/* 头像 */}
              <div className="mx-auto mb-4 h-20 w-20 rounded-full bg-gradient-to-br from-[var(--theme-primary)]/30 to-[var(--theme-accent)]/30 flex items-center justify-center">
                <User className="h-10 w-10 text-white/30" />
              </div>

              <h3 className="text-xl font-bold text-center mb-1">
                {selectedChar.name}
              </h3>

              <div className="flex items-start gap-2 mb-4 justify-center">
                <Quote className="h-3 w-3 text-[var(--muted-foreground)] flex-shrink-0 mt-0.5" />
                <p className="text-sm italic text-[var(--muted-foreground)] text-center">
                  &ldquo;{selectedChar.tagline}&rdquo;
                </p>
              </div>

              <div className="space-y-3 mb-6">
                <div>
                  <p className="text-xs font-bold text-[var(--muted-foreground)] mb-1">
                    性格
                  </p>
                  <p className="text-sm">{selectedChar.personality}</p>
                </div>
                <div>
                  <p className="text-xs font-bold text-[var(--muted-foreground)] mb-1">
                    背景
                  </p>
                  <p className="text-sm text-[var(--muted-foreground)]">
                    {selectedChar.background}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold text-[var(--muted-foreground)] mb-1">
                    擅长
                  </p>
                  <p className="text-sm text-[var(--muted-foreground)]">
                    {selectedChar.knows?.join("、")}
                  </p>
                </div>
              </div>

              <button
                onClick={() => setSelectedChar(null)}
                className="w-full rounded-lg bg-[var(--accent)] py-2.5 text-sm transition-colors hover:bg-[var(--muted)]"
              >
                关闭
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.main>
  );
}
