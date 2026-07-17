/**
 * LibraryPage — 剧本库
 *
 * 第一印象决定一切。这个页面要让玩家感觉"我即将进入一个神秘的世界"。
 * 采用电影化布局：全屏主视觉 + 精致卡片网格
 */

"use client";

import { motion } from "framer-motion";
import { Sparkles, Clock, Star } from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.25, 0.1, 0.25, 1] } },
};

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

const stableRandom = (index: number, salt: number) => {
  const value = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453;
  return value - Math.floor(value);
};

const cssNumber = (value: number) => value.toFixed(4);
const cssPercent = (value: number) => `${cssNumber(value)}%`;
const cssPx = (value: number) => `${cssNumber(value)}px`;
const cssSeconds = (value: number) => `${cssNumber(value)}s`;

type ParticleStyle = {
  readonly left: string;
  readonly top: string;
  readonly width: string;
  readonly height: string;
  readonly opacity: string;
  readonly animation?: string;
  readonly filter?: string;
};

const heroSnowflakes: readonly ParticleStyle[] = Array.from({ length: 30 }, (_, index) => ({
  left: cssPercent(stableRandom(index, 1) * 100),
  top: cssPx(-(2 + stableRandom(index, 2) * 4)),
  width: cssPx(1.5 + stableRandom(index, 3) * 2.5),
  height: cssPx(1.5 + stableRandom(index, 4) * 2.5),
  opacity: cssNumber(0.2 + stableRandom(index, 5) * 0.3),
  animation: `snow-fall ${cssSeconds(8 + stableRandom(index, 6) * 10)} -${cssSeconds(stableRandom(index, 7) * 10)} linear infinite`,
  filter: "blur(0.5px)",
}));

const cardSnowSpecks: readonly ParticleStyle[] = Array.from({ length: 15 }, (_, index) => ({
  left: cssPercent(stableRandom(index, 11) * 100),
  top: cssPercent(stableRandom(index, 12) * 100),
  width: cssPx(1 + stableRandom(index, 13) * 2),
  height: cssPx(1 + stableRandom(index, 14) * 2),
  opacity: cssNumber(0.3 + stableRandom(index, 15) * 0.5),
}));

const pkg = {
  id: "snow-village",
  title: "雪乡连环杀人事件",
  subtitle: "AI 沉浸式悬疑互动剧",
  tagline: "雪乡，一个被大雪覆盖的东北村庄。除夕夜，一桩离奇的命案打破了这份宁静。",
  difficulty: 3,
  duration: 120,
  genre: ["悬疑", "推理", "惊悚"],
  rating: 4.5,
  players: "1人 · 单人沉浸",
};

export default function LibraryPage() {
  return (
    <main className="min-h-screen bg-[var(--background)]">
      {/* ══ 全屏主视觉 ══ */}
      <section className="relative h-screen w-full overflow-hidden">
        {/* 背景层 */}
        <div className="absolute inset-0">
          <div className="absolute inset-0 bg-gradient-to-b from-[#0f0f23] via-[#1a1a3e] to-[#0a0a0b]" />
          {/* 雪花粒子 */}
          <div className="absolute inset-0 overflow-hidden">
            {heroSnowflakes.map((snowflake, i) => (
              <div
                key={i}
                className="absolute rounded-full bg-white"
                style={snowflake}
              />
            ))}
          </div>
          {/* 底部渐隐 */}
          <div className="absolute inset-x-0 bottom-0 h-[40vh] bg-gradient-to-t from-[var(--background)] to-transparent" />
        </div>

        {/* 内容层 */}
        <div className="relative z-10 flex h-full flex-col items-center justify-center px-6 text-center">
          <motion.p
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="mb-3 text-xs tracking-[0.3em] text-white/30 uppercase"
          >
            {pkg.subtitle}
          </motion.p>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="mb-4 text-5xl md:text-7xl font-bold text-white tracking-tight"
          >
            {pkg.title}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            className="mb-8 max-w-xl text-sm md:text-base text-white/50 leading-relaxed"
          >
            {pkg.tagline}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.8 }}
            className="flex flex-wrap items-center justify-center gap-3 mb-10"
          >
            {pkg.genre.map((g) => (
              <span key={g}
                className="rounded-full border border-white/10 px-4 py-1.5 text-xs text-white/50 tracking-wider"
              >
                {g}
              </span>
            ))}
            <span className="flex items-center gap-1 text-white/30 text-xs">·</span>
            <span className="flex items-center gap-1 text-white/50 text-xs">
              <Star className="h-3 w-3 text-[var(--warning)]" />
              {pkg.rating}
            </span>
            <span className="flex items-center gap-1 text-white/50 text-xs">
              <Clock className="h-3 w-3" />
              {pkg.duration}分钟
            </span>
          </motion.div>

          <motion.a
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 1.0 }}
            href="/library/snow-village"
            className="group relative inline-flex items-center gap-2 rounded-sm border border-[#c7aa6b]/30 bg-[#121513]/75 px-8 py-3.5 text-sm font-bold tracking-[0.12em] text-[#e7ddc3] transition-all hover:border-[#d4b978]/60 hover:bg-[#1b1e1a] shadow-xl shadow-black/30"
          >
            <Sparkles className="h-4 w-4 text-[#c7aa6b]" />
            体验可走动地图 Demo
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#c7aa6b] opacity-60" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-[#c7aa6b]" />
            </span>
          </motion.a>
        </div>

        {/* 底部滚动提示 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10"
        >
          <div className="flex flex-col items-center gap-2 text-white/20 text-xs">
            <span>探索更多剧本</span>
            <svg className="w-4 h-4 animate-bounce" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </div>
        </motion.div>
      </section>

      {/* ══ 剧本库 ══ */}
      <section className="relative px-6 pb-24 -mt-20">
        <div className="mx-auto max-w-6xl">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-8 text-lg font-bold text-white/80"
          >
            剧本库
          </motion.h2>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true }}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"
          >
            {/* 雪乡卡片 */}
            <motion.a
              variants={fadeUp}
              href={`/library/${pkg.id}`}
              className="group relative rounded-2xl overflow-hidden border border-white/5 bg-white/[0.03] hover:bg-white/[0.06] hover:border-white/10 transition-all duration-500"
            >
              {/* 卡片顶部氛围图 */}
              <div className="h-48 bg-gradient-to-br from-[#1a1a3e] via-[#2a1a3e] to-[#0a0a0b] relative overflow-hidden">
                <div className="absolute inset-0 opacity-20">
                  {cardSnowSpecks.map((snowflake, i) => (
                    <div key={i} className="absolute rounded-full bg-white"
                      style={snowflake} />
                  ))}
                </div>
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                <div className="absolute bottom-3 left-4">
                  <div className="flex gap-2">
                    {pkg.genre.slice(0, 2).map((g) => (
                      <span key={g} className="rounded-full bg-black/40 backdrop-blur-sm px-2.5 py-0.5 text-[10px] text-white/60 border border-white/5">
                        {g}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* 卡片内容 */}
              <div className="p-5">
                <h3 className="text-base font-bold text-white mb-1.5 group-hover:text-[var(--theme-primary)] transition-colors">
                  {pkg.title}
                </h3>
                <p className="text-sm text-white/40 line-clamp-2 mb-4 leading-relaxed">
                  {pkg.tagline}
                </p>
                <div className="flex items-center justify-between text-xs text-white/30">
                  <span className="flex items-center gap-1">
                    <Star className="h-3 w-3 text-[var(--warning)]" />
                    {pkg.rating}
                  </span>
                  <span>{pkg.players}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {pkg.duration}min
                  </span>
                </div>
              </div>
            </motion.a>

            {/* 占位卡片（更多剧本即将上线） */}
            <motion.div
              variants={fadeUp}
              className="rounded-2xl border border-dashed border-white/5 p-8 flex flex-col items-center justify-center text-center h-[350px] bg-white/[0.02]"
            >
              <p className="text-3xl mb-3 opacity-30">🎭</p>
              <p className="text-sm text-white/20">更多剧本即将上线</p>
            </motion.div>
          </motion.div>
        </div>
      </section>
    </main>
  );
}
