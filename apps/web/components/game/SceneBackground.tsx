/**
 * SceneBackground — 沉浸场景背景
 *
 * 场景是游戏的主视觉，不能只是渐变色。
 * 每一帧画面都应该是美的、有氛围的。
 *
 * 特性：
 * - 每个场景独立的环境粒子（雪/火光/阴影）
 * - 动态暗角随紧张度变化
 * - 场景切换时电影级过渡
 * - 低性能设备自动降级
 */

"use client";

import { useMemo, useRef, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/stores/gameStore";

/* ── 场景环境配置 ── */
interface SceneAtmosphere {
  name: string;
  gradient: string;
  accent: string;
  particles: "snow" | "embers" | "none";
  particleCount: number;
  vignette: number;        // 暗角强度 0-1
  ambientSound: string;
  hasFlicker: boolean;     // 是否有闪烁光源
}

const sceneAtmospheres: Record<string, SceneAtmosphere> = {
  village_entrance: {
    name: "雪乡村口",
    gradient: "linear-gradient(180deg, #0f0f23 0%, #1a1a3e 30%, #16213e 60%, #0d1117 100%)",
    accent: "#4a6fa5",
    particles: "snow",
    particleCount: 40,
    vignette: 0.55,
    ambientSound: "风雪声",
    hasFlicker: false,
  },
  restaurant_hall: {
    name: "饭店大厅",
    gradient: "linear-gradient(180deg, #2a1a10 0%, #3d2818 30%, #2e1f12 60%, #1a1410 100%)",
    accent: "#c4854a",
    particles: "embers",
    particleCount: 12,
    vignette: 0.45,
    ambientSound: "炉火噼啪声",
    hasFlicker: true,
  },
  crime_scene: {
    name: "案发现场",
    gradient: "linear-gradient(180deg, #0a0510 0%, #1a0a1a 25%, #0f0a15 55%, #05050a 100%)",
    accent: "#8b2f3f",
    particles: "none",
    particleCount: 0,
    vignette: 0.75,
    ambientSound: "死寂",
    hasFlicker: false,
  },
  back_alley: {
    name: "后门小巷",
    gradient: "linear-gradient(180deg, #05050f 0%, #0a0a1a 30%, #0d0d1a 60%, #08080f 100%)",
    accent: "#3a3a6a",
    particles: "snow",
    particleCount: 25,
    vignette: 0.7,
    ambientSound: "寒风呼啸",
    hasFlicker: false,
  },
};

const stableRandom = (index: number, salt: number) => {
  const value = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453;
  return value - Math.floor(value);
};

const cssNumber = (value: number) => value.toFixed(4);
const cssPercent = (value: number) => `${cssNumber(value)}%`;
const cssPx = (value: number) => `${cssNumber(value)}px`;
const cssSeconds = (value: number) => `${cssNumber(value)}s`;

/* ── 雪花粒子 ── */
function SnowParticles({ count }: { count: number }) {
  const particles = useMemo(() =>
    Array.from({ length: count }, (_, i) => {
      const size = 1.5 + stableRandom(i, 2) * 3;
      return {
        id: i,
        left: cssPercent(stableRandom(i, 1) * 100),
        top: cssPx(-(size * 2)),
        size: cssPx(size),
        opacity: cssNumber(0.3 + stableRandom(i, 3) * 0.5),
        duration: cssSeconds(6 + stableRandom(i, 4) * 8),
        delay: cssSeconds(stableRandom(i, 5) * 10),
        drift: cssPx(stableRandom(i, 6) * 40 - 20),
      };
    }),
    [count]
  );

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-10">
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute rounded-full bg-white"
          style={{
            left: p.left,
            top: p.top,
            width: p.size,
            height: p.size,
            opacity: p.opacity,
            animation: `snow-fall ${p.duration} -${p.delay} linear infinite`,
            transform: `translateX(${p.drift})`,
            filter: "blur(0.5px)",
          }}
        />
      ))}
    </div>
  );
}

/* ── 火星粒子（炉火） ── */
function EmberParticles({ count }: { count: number }) {
  const particles = useMemo(() =>
    Array.from({ length: count }, (_, i) => ({
      id: i,
      left: cssPercent(35 + stableRandom(i, 11) * 30),
      size: cssPx(1.5 + stableRandom(i, 12) * 2),
      opacity: cssNumber(0.4 + stableRandom(i, 13) * 0.4),
      duration: cssSeconds(2 + stableRandom(i, 14) * 3),
      delay: cssSeconds(stableRandom(i, 15) * 3),
    })),
    [count]
  );

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-10">
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute bottom-[15%] rounded-full"
          style={{
            left: p.left,
            width: p.size,
            height: p.size,
            opacity: p.opacity,
            background: `radial-gradient(circle, #ff8844, #ff4422)`,
            animation: `ember-rise ${p.duration} -${p.delay} ease-out infinite`,
            filter: "blur(0.5px)",
            boxShadow: "0 0 6px #ff442244",
          }}
        />
      ))}
    </div>
  );
}

/* ── 场景装饰层 ── */
function SceneDecor({ sceneId, atmosphere }: { sceneId: string; atmosphere: SceneAtmosphere }) {
  if (sceneId === "restaurant_hall") {
    return (
      <>
        {/* 窗户光效 */}
        <div className="absolute top-[15%] right-[10%] w-[25%] h-[30%] opacity-[0.08]">
          <div className="w-full h-full bg-gradient-to-b from-[#ff8844] to-transparent rounded-sm"
            style={{ animation: "flicker 4s ease-in-out infinite" }} />
        </div>
        {/* 横梁阴影 */}
        <div className="absolute top-[5%] left-0 right-0 h-[3%] bg-black/30" />
        <div className="absolute top-[5%] left-0 right-0 h-[3%] bg-black/20 transform -translate-y-[60%]" />
      </>
    );
  }

  if (sceneId === "crime_scene") {
    return (
      <>
        {/* 警戒线 */}
        <div className="absolute top-[45%] left-[5%] right-[5%] border-t-2 border-[var(--warning)]/20"
          style={{ borderStyle: "dashed" }} />
        <div className="absolute top-[45%] left-[5%] right-[5%] border-t-2 border-[var(--warning)]/10"
          style={{ borderStyle: "dashed", transform: "translateY(-8px)" }} />
        {/* 月光 */}
        <div className="absolute top-[8%] left-[60%] w-[20%] h-[15%]"
          style={{
            background: "radial-gradient(ellipse, rgba(200,200,255,0.06), transparent)",
            filter: "blur(20px)",
          }} />
      </>
    );
  }

  if (sceneId === "back_alley") {
    return (
      <>
        {/* 墙轮廓 */}
        <div className="absolute left-[5%] top-0 w-[25%] h-full bg-gradient-to-r from-black/40 to-transparent" />
        <div className="absolute right-[5%] top-0 w-[25%] h-full bg-gradient-to-l from-black/40 to-transparent" />
        {/* 月光 */}
        <div className="absolute top-[5%] left-[45%] w-[10%] h-[20%]"
          style={{
            background: "linear-gradient(180deg, rgba(200,200,255,0.08), transparent)",
            filter: "blur(10px)",
          }} />
      </>
    );
  }

  return null;
}

/* ── 主组件 ── */
export function SceneBackground() {
  const currentScene = useGameStore((s) => s.currentScene);
  const [tensionLevel, setTensionLevel] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const atmosphere = sceneAtmospheres[currentScene] || sceneAtmospheres.village_entrance;

  // 环境音模拟
  useEffect(() => {
    // 实际项目中这里连接 Howler.js
    // Mock：无实际操作
  }, [currentScene]);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={currentScene}
        className="absolute inset-0 z-10"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.8, ease: "easeInOut" }}
      >
        {/* 层1: 渐变背景 */}
        <div
          className="absolute inset-0"
          style={{ background: atmosphere.gradient }}
        />

        {/* 层2: 纹理叠加 */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
            backgroundSize: "256px 256px",
          }}
        />

        {/* 层3: 场景装饰 */}
        <SceneDecor sceneId={currentScene} atmosphere={atmosphere} />

        {/* 层4: 环境粒子 */}
        {atmosphere.particles === "snow" && atmosphere.particleCount > 0 && (
          <SnowParticles count={atmosphere.particleCount} />
        )}
        {atmosphere.particles === "embers" && atmosphere.particleCount > 0 && (
          <EmberParticles count={atmosphere.particleCount} />
        )}

        {/* 层5: 闪烁光源 */}
        {atmosphere.hasFlicker && (
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ animation: "flicker 3s ease-in-out infinite" }}
          >
            <div
              className="absolute bottom-[20%] left-[30%] w-[40%] h-[25%]"
              style={{
                background: `radial-gradient(ellipse at 50% 100%, ${atmosphere.accent}22, transparent 70%)`,
              }}
            />
          </div>
        )}

        {/* 层6: 动态暗角（随紧张度变化） */}
        <div
          className="absolute inset-0 transition-all duration-[2000ms] ease-in-out pointer-events-none"
          style={{
            background: `
              radial-gradient(
                ellipse at center,
                transparent ${35 - tensionLevel * 15}%,
                rgba(0,0,0,${atmosphere.vignette + tensionLevel * 0.25}) 100%
              )
            `,
            opacity: 0.6 + tensionLevel * 0.3,
          }}
        />

        {/* 层7: 底部渐变过渡到UI */}
        <div
          className="absolute bottom-0 left-0 right-0 h-[30vh] pointer-events-none"
          style={{
            background: "linear-gradient(180deg, transparent 0%, var(--background) 100%)",
            opacity: 0.3,
          }}
        />

        {/* 层8: 场景名标签（淡入） */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5, duration: 0.6 }}
          className="absolute top-4 left-4 z-20"
        >
          <div className="flex items-center gap-2 rounded-lg bg-black/40 backdrop-blur-sm px-3 py-1.5 border border-white/5">
            <span className="text-xs text-white/70 font-medium tracking-wider">
              {atmosphere.name}
            </span>
            <span className="text-[10px] text-white/30">·</span>
            <span className="text-[10px] text-white/30 tracking-wider">
              {atmosphere.ambientSound}
            </span>
          </div>
        </motion.div>

        {/* 层9: 紧张指示器（仅紧张时显示） */}
        {tensionLevel > 0.4 && (
          <div
            className="absolute inset-0 pointer-events-none z-20"
            style={{
              background: `radial-gradient(ellipse at center, transparent 50%, rgba(220,38,38,${tensionLevel * 0.1}) 100%)`,
              transition: "opacity 2s ease",
            }}
          />
        )}
      </motion.div>
    </AnimatePresence>
  );
}
