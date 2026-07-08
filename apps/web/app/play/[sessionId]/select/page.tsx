/**
 * CharacterSelectPage — 角色选择
 *
 * 这是玩家"成为角色"的瞬间，必须有仪式感。
 * 采用电影选角风格：全屏角色展示 + Embla 滑动切换
 *
 * 桌面: 并排卡片 + 左右箭头
 * 手机: 全屏 embla-carousel 滑动
 */

"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { toast } from "sonner";

const characters = [
  {
    id: "zhuosiyuan", name: "卓司元",
    tag: "「我是个普通的游客……只是碰巧注意到了一些细节。」",
    personality: "细心 · 谨慎 · 观察力敏锐",
    background: "来自城市的保险调查员，因年假来到雪乡度假。职业习惯让他对周围的一切都保持警惕。",
    color: "#22c55e",
    gradient: "from-emerald-900/40 via-emerald-800/20 to-transparent",
  },
  {
    id: "cuikaiqiang", name: "崔铠强",
    tag: "「这村子有问题，我敢肯定。」",
    personality: "冲动 · 直率 · 行动派",
    background: "退伍军人，性格暴躁但正义感强。曾来过雪乡一次，对这里有些模糊的记忆。",
    color: "#f59e0b",
    gradient: "from-amber-900/40 via-amber-800/20 to-transparent",
  },
  {
    id: "likaixin", name: "李开心",
    tag: "「大家冷静一下！一定能找到真相的。」",
    personality: "温暖 · 善良 · 共情力强",
    background: "小学教师，天性乐观善良。来雪乡是为了拍摄雪景照片。",
    color: "#ec4899",
    gradient: "from-pink-900/40 via-pink-800/20 to-transparent",
  },
  {
    id: "wangqi", name: "王琪",
    tag: "「我……我昨晚好像看到了什么……」",
    personality: "胆小 · 敏感 · 直觉敏锐",
    background: "自由撰稿人，来雪乡寻找创作灵感。性格软弱但第六感极强。",
    color: "#3b82f6",
    gradient: "from-blue-900/40 via-blue-800/20 to-transparent",
  },
  {
    id: "xiaomeng", name: "萧萌",
    tag: "「哇！这里好像侦探小说里的场景！」",
    personality: "天真 · 活泼 · 好奇心强",
    background: "大学生，寒假和朋友一起来雪乡玩。喜欢看推理小说，没想到自己会身临其境。",
    color: "#a855f7",
    gradient: "from-purple-900/40 via-purple-800/20 to-transparent",
  },
  {
    id: "chenji", name: "陈吉",
    tag: "「呵呵，越来越有意思了。」",
    personality: "冷静 · 理性 · 高深莫测",
    background: "神秘商人，没人知道他的真实身份。总是面带微笑，但眼神中藏着什么。",
    color: "#6b7280",
    gradient: "from-gray-800/40 via-gray-700/20 to-transparent",
  },
];

export default function CharacterSelectPage() {
  const params = useParams();
  const router = useRouter();
  const scriptId = params.sessionId as string;

  const [selected, setSelected] = useState(0);
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(false);

  const current = characters[selected];

  const handlePrev = () => setSelected((s) => (s - 1 + characters.length) % characters.length);
  const handleNext = () => setSelected((s) => (s + 1) % characters.length);

  const handleSelect = async () => {
    setLocked(true);
    setLoading(true);
    // 模拟API调用
    await new Promise((r) => setTimeout(r, 1200));
    const sessionId = `session-${Date.now()}`;
    router.push(`/play/${sessionId}`);
    toast("角色已锁定", { description: `你选择了${current.name}`, icon: "🎭" });
  };

  return (
    <main className="relative h-screen w-full overflow-hidden bg-[var(--background)]">
      {/* ══ 背景层 ══ */}
      <div className={`absolute inset-0 bg-gradient-to-b ${current.gradient} transition-all duration-700`} />
      <div className="absolute inset-0 bg-gradient-to-t from-[var(--background)] via-transparent to-[var(--background)]/50" />
      <div className="absolute inset-0" style={{
        backgroundImage: `radial-gradient(ellipse at 50% 0%, ${current.color}11, transparent 60%)`,
      }} />

      {/* ══ 返回按钮 ══ */}
      <button
        onClick={() => router.back()}
        className="absolute top-4 left-4 z-20 w-9 h-9 flex items-center justify-center rounded-lg bg-black/40 backdrop-blur-sm border border-white/5 text-white/60 hover:text-white/90 transition-all"
      >
        <ArrowLeft className="h-4 w-4" />
      </button>

      {/* ══ 主内容 ══ */}
      <div className="relative z-10 flex h-full flex-col items-center justify-center px-6 pb-24">
        {/* 标题 */}
        <motion.p
          key={current.id}
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-2 text-xs tracking-[0.2em] text-white/30 uppercase"
        >
          选择你的身份
        </motion.p>

        {/* 角色卡 */}
        <div className="relative w-full max-w-md mx-auto mb-8">
          {/* 角色头像 */}
          <div className="flex justify-center mb-6">
            <motion.div
              key={`avatar-${current.id}`}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", damping: 15, stiffness: 200 }}
              className="relative"
            >
              <div
                className="w-32 h-32 md:w-40 md:h-40 rounded-full flex items-center justify-center text-4xl md:text-5xl border-4"
                style={{
                  borderColor: `${current.color}40`,
                  backgroundColor: `${current.color}10`,
                  boxShadow: `0 0 40px ${current.color}20`,
                }}
              >
                {current.id === "zhuosiyuan" ? "🔍" :
                 current.id === "cuikaiqiang" ? "💪" :
                 current.id === "likaixin" ? "😊" :
                 current.id === "wangqi" ? "👁️" :
                 current.id === "xiaomeng" ? "📚" : "🎩"}
              </div>
              {/* 选中光环 */}
              <div
                className="absolute inset-0 rounded-full animate-ping opacity-20"
                style={{ boxShadow: `0 0 30px ${current.color}`, animation: "pulse-ring 2s ease-in-out infinite" }}
              />
            </motion.div>
          </div>

          {/* 角色信息 */}
          <AnimatePresence mode="wait">
            <motion.div
              key={current.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
              className="text-center"
            >
              <h2 className="text-3xl font-bold text-white mb-2">{current.name}</h2>
              <p className="text-sm text-white/50 italic mb-4">{current.tag}</p>
              <div
                className="inline-block rounded-full px-3 py-1 text-xs mb-4"
                style={{ backgroundColor: `${current.color}15`, color: current.color }}
              >
                {current.personality}
              </div>
              <p className="text-sm text-white/40 max-w-md mx-auto leading-relaxed px-4">
                {current.background}
              </p>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* 导航箭头 */}
        <div className="flex items-center gap-6 mb-8">
          <button
            onClick={handlePrev}
            disabled={locked}
            className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-white/50 hover:text-white hover:border-white/20 hover:bg-white/5 transition-all disabled:opacity-30"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>

          {/* 缩略图指示器 */}
          <div className="flex gap-2">
            {characters.map((c, i) => (
              <button
                key={c.id}
                onClick={() => !locked && setSelected(i)}
                className={`w-2 h-2 rounded-full transition-all duration-300 ${
                  i === selected
                    ? "w-6"
                    : "hover:bg-white/30"
                }`}
                style={{
                  backgroundColor: i === selected ? current.color : "rgba(255,255,255,0.15)",
                }}
              />
            ))}
          </div>

          <button
            onClick={handleNext}
            disabled={locked}
            className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-white/50 hover:text-white hover:border-white/20 hover:bg-white/5 transition-all disabled:opacity-30"
          >
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>

        {/* 确认选择按钮 */}
        <motion.button
          onClick={handleSelect}
          disabled={locked}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="relative flex items-center gap-3 rounded-xl bg-[var(--theme-primary)] px-10 py-3.5 text-sm font-bold text-white transition-all hover:bg-[var(--theme-primary)]/80 disabled:opacity-60 shadow-xl shadow-[var(--theme-primary)]/20"
        >
          {loading ? (
            <>
              <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              锁定角色中…
            </>
          ) : locked ? (
            <>
              <Check className="h-4 w-4" />
              已锁定
            </>
          ) : (
            <>
              <Check className="h-4 w-4" />
              选择 {current.name}
            </>
          )}
        </motion.button>
      </div>
    </main>
  );
}
