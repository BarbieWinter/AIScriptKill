/**
 * EmotionIndicator - NPC 情绪指示器
 * 显示角色当前情绪图标 + 文字描述
 * 情绪变化时带动画
 */

"use client";

import { motion, AnimatePresence } from "framer-motion";

interface EmotionIndicatorProps {
  emotion: string;
  characterName: string;
  size?: "sm" | "md" | "lg";
}

const emotionIcons: Record<string, string> = {
  normal: "😐",
  calm: "😊",
  happy: "😄",
  slightly_nervous: "😅",
  nervous: "😰",
  defensive: "😤",
  cold: "😑",
  slightly_agitated: "😠",
  shocked: "😱",
  fear: "😨",
  scared: "😰",
  sad: "😢",
  thinking: "🤔",
  serious: "😐",
  angry: "😡",
  lying: "😏",
  suspicious: "🤨",
  shifty: "😏",
};

const emotionColors: Record<string, string> = {
  normal: "text-white/80",
  calm: "text-white/80",
  happy: "text-green-400",
  slightly_nervous: "text-yellow-400",
  nervous: "text-yellow-400",
  defensive: "text-orange-400",
  cold: "text-blue-300",
  slightly_agitated: "text-orange-400",
  shocked: "text-red-400",
  fear: "text-red-400",
  scared: "text-red-400",
  sad: "text-blue-300",
  thinking: "text-purple-400",
  serious: "text-white/60",
  angry: "text-red-500",
  lying: "text-yellow-300",
  suspicious: "text-purple-300",
  shifty: "text-orange-300",
};

export function EmotionIndicator({
  emotion,
  characterName,
  size = "md",
}: EmotionIndicatorProps) {
  const icon = emotionIcons[emotion] || "😐";
  const color = emotionColors[emotion] || "text-white/80";

  const sizeMap = { sm: "text-sm", md: "text-base", lg: "text-lg" };
  const iconSize = { sm: "text-base", md: "text-xl", lg: "text-2xl" };

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={emotion}
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.5, opacity: 0 }}
        transition={{ duration: 0.2 }}
        className={`flex items-center gap-1.5 ${sizeMap[size]}`}
      >
        <span className={iconSize[size]}>{icon}</span>
        <span className={`${color} text-xs`}>
          {characterName}
        </span>
      </motion.div>
    </AnimatePresence>
  );
}
