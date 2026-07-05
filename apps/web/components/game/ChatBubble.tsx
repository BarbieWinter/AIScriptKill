/**
 * ChatBubble - 聊天消息气泡
 * DM: 居中斜体（特殊样式）
 * NPC: 左对齐 + 情绪样式
 * 玩家: 右对齐（主题色背景）
 */

"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface ChatBubbleProps {
  message: {
    id: string;
    role: string;
    character_id?: string | null;
    text: string;
    emotion?: string;
    timestamp?: string;
  };
  characterName?: string;
}

export function ChatBubble({ message, characterName }: ChatBubbleProps) {
  const { role, text, emotion } = message;
  const isDM = message.character_id === "dm" || role === "dm";
  const isNPC = role === "npc" && !isDM;
  const isPlayer = role === "player";

  // 玩家气泡
  if (isPlayer) {
    return (
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.3 }}
        className="flex justify-end mb-3"
      >
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-[var(--theme-primary)]/20 px-4 py-2.5 border border-[var(--theme-primary)]/20">
          <p className="text-sm text-[var(--foreground)]">{text}</p>
        </div>
      </motion.div>
    );
  }

  // DM 旁白（居中斜体）
  if (isDM) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-3"
      >
        <p className="dm-narration text-sm">{text}</p>
      </motion.div>
    );
  }

  // NPC 气泡（左对齐）
  const isLying = emotion === "lying" || emotion === "shifty";
  const isFear = emotion === "fear" || emotion === "scared" || emotion === "shocked";
  const isNervous = emotion === "nervous" || emotion === "defensive";

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        "flex mb-3",
        isFear && "npc-emotion-shaken"
      )}
    >
      <div className="max-w-[80%]">
        {/* 角色名 */}
        {characterName && (
          <p className="text-xs font-bold text-[var(--muted-foreground)] mb-1 ml-1">
            {characterName}
          </p>
        )}
        <div
          className={cn(
            "rounded-2xl rounded-bl-md px-4 py-2.5 border",
            isLying
              ? "border-l-2 border-[var(--danger)] bg-[rgba(220,38,38,0.05)]"
              : isNervous
              ? "border-[var(--warning)]/30 bg-[var(--accent)]"
              : "bg-[var(--accent)] border-[var(--border)]"
          )}
        >
          <p
            className={cn(
              "text-sm",
              isFear && "text-[var(--danger)]",
              isNervous && "text-[var(--warning)]"
            )}
          >
            {text}
          </p>
        </div>
      </div>
    </motion.div>
  );
}
