/**
 * ChatPanel — 沉浸式对话面板
 *
 * 不是"聊天软件"，是"视觉小说式"的叙事对话。
 * 场景是主角，对话是场景的一部分。
 *
 * 设计原则：
 * - 浮在场景底部的半透明面板（不是分割线）
 * - 对话气泡从下往上依次显现（类似字幕）
 * - NPC情绪通过文字样式+图标+动画三重表达
 * - 玩家输入是优雅的底部文本框（不突兀）
 */

"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore, type ActionType } from "@/stores/gameStore";
import { api, isMockMode } from "@/lib/api";
import { getMockEngine } from "@/lib/mock-data";
import { toast } from "sonner";
import { Send, ChevronUp, Sparkles } from "lucide-react";

/* ── NPC 配置 ── */
const npcConfig: Record<string, { name: string; color: string; icon: string }> = {
  dm:         { name: "DM",        color: "#3b82f6", icon: "🎭" },
  wangdada:   { name: "王大达",     color: "#7c3aed", icon: "👨‍🍳" },
  chengjun:   { name: "程俊",       color: "#dc2626", icon: "🔪" },
  zhuosiyuan: { name: "卓司元",     color: "#22c55e", icon: "🔍" },
  cuikaiqiang:{ name: "崔铠强",     color: "#f59e0b", icon: "💪" },
  likaixin:   { name: "李开心",     color: "#ec4899", icon: "😊" },
};

const emotionIcons: Record<string, string> = {
  normal: "😐",
  calm: "😌",
  serious: "🧐",
  slightly_nervous: "😅",
  nervous: "😰",
  defensive: "😤",
  cold: "😑",
  slightly_agitated: "😠",
  shocked: "😱",
  fear: "😨",
  sad: "😢",
};

/* ── 打字指示器 ── */
function TypingDots({ charName }: { charName: string }) {
  return (
    <div className="flex items-center gap-2 px-4 py-2">
      <span className="text-sm text-white/50">{charName}</span>
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-white/40 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.8s" }}
          />
        ))}
      </span>
    </div>
  );
}

/* ── 对话气泡 ── */
function MessageBubble({ msg }: { msg: any }) {
  const isDM = msg.character_id === "dm";
  const isPlayer = msg.role === "player";
  const config = npcConfig[msg.character_id];
  const emotion = msg.emotion || "normal";
  const emotionIcon = emotionIcons[emotion] || "😐";

  if (isDM) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center px-6 py-1.5"
      >
        <div className="dm-narration max-w-2xl w-full">
          <p className="text-sm leading-relaxed text-white/70">
            {msg.text}
          </p>
        </div>
      </motion.div>
    );
  }

  if (isPlayer) {
    return (
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex justify-end px-4 py-1"
      >
        <div className="max-w-[80%] md:max-w-[60%]">
          <p className="text-sm leading-relaxed bg-[var(--theme-primary)]/20 text-white/90 rounded-2xl rounded-br-md px-4 py-2.5 border border-[var(--theme-primary)]/10">
            {msg.text}
          </p>
        </div>
      </motion.div>
    );
  }

  // NPC 对话
  const emotionStyles: Record<string, string> = {
    defensive: "border-l-[var(--warning)] bg-[var(--warning)]/5",
    nervous: "border-l-[var(--warning)] bg-[var(--warning)]/5",
    fear: "border-l-[var(--danger)] bg-[var(--danger)]/5",
    shocked: "border-l-[var(--danger)] bg-[var(--danger)]/5",
    slightly_agitated: "border-l-[var(--danger)] bg-[var(--danger)]/5",
    cold: "border-l-[var(--info)] bg-[var(--info)]/5 opacity-80",
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-start gap-3 px-4 py-1"
    >
      {/* NPC 头像圆点 */}
      <div
        className="mt-2 w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 border"
        style={{
          backgroundColor: `${config?.color}15`,
          borderColor: `${config?.color}30`,
        }}
      >
        <span className="text-xs">{config?.icon || "?"}</span>
      </div>

      <div className="flex-1 min-w-0">
        {/* 角色名 + 情绪 */}
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-medium" style={{ color: config?.color }}>
            {config?.name || msg.character_id}
          </span>
          <span className="text-xs" title={emotion}>
            {emotionIcon}
          </span>
        </div>

        {/* 对话文本 */}
        <div
          className={`
            rounded-2xl rounded-tl-md px-4 py-2.5 border border-white/5
            ${emotionStyles[emotion] || "bg-white/5"}
            ${emotion === "fear" || emotion === "shocked" ? "npc-emotion-shocked" : ""}
          `}
        >
          <p className={`text-sm leading-relaxed ${emotion === "fear" ? "text-[var(--danger)]" : "text-white/85"}`}>
            {msg.text}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

/* ── 主组件 ── */
export function ChatPanel() {
  const chatMessages = useGameStore((s) => s.chatMessages);
  const isNpcTyping = useGameStore((s) => s.isNpcTyping);
  const typingCharacterId = useGameStore((s) => s.typingCharacterId);
  const addMessage = useGameStore((s) => s.addMessage);
  const setNpcTyping = useGameStore((s) => s.setNpcTyping);
  const availableCharacters = useGameStore((s) => s.availableCharacters);
  const currentStage = useGameStore((s) => s.currentStage);
  const sessionId = useGameStore((s) => s.sessionId);
  const setStage = useGameStore((s) => s.setStage);
  const setScene = useGameStore((s) => s.setScene);
  const setActions = useGameStore((s) => s.setActions);

  const [inputText, setInputText] = useState("");
  const [selectedChar, setSelectedChar] = useState("wangdada");
  const [showCharMenu, setShowCharMenu] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const shouldFollowLatestRef = useRef(true);

  // 只在玩家仍停留在底部时跟随新消息；向上翻阅历史时不强制拉回底部。
  useEffect(() => {
    if (!shouldFollowLatestRef.current) return;
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatMessages, isNpcTyping]);

  const handleMessagesScroll = () => {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    const distanceFromBottom =
      viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
    shouldFollowLatestRef.current = distanceFromBottom < 48;
  };

  /** 发送消息 → 触发 NPC 回复 */
  const handleSend = useCallback(async () => {
    const text = inputText.trim();
    if (!text || !sessionId || isNpcTyping) return;

    shouldFollowLatestRef.current = true;
    addMessage({
      id: `msg-p-${Date.now()}`,
      role: "player",
      character_id: null,
      text,
      timestamp: new Date().toISOString(),
    });
    setInputText("");
    setNpcTyping(selectedChar);

    try {
      if (isMockMode()) {
        const response = getMockEngine().sendMessage(selectedChar, text);
        if (response) {
          addMessage({
            id: `msg-n-${Date.now()}`,
            role: "npc",
            character_id: selectedChar,
            text: response.text,
            emotion: response.emotion,
            timestamp: new Date().toISOString(),
          });
        }
        return;
      }

      const response = await api.performAction(sessionId, "talk_to_npc", {
        character_id: selectedChar,
        message: text,
      });
      if (response.type === "npc_response") {
        addMessage({
          id: `msg-n-${Date.now()}`,
          role: "npc",
          character_id: response.character_id,
          text: response.text,
          emotion: response.emotion,
          timestamp: new Date().toISOString(),
        });
      }
    } catch (error) {
      console.error("[ChatPanel] NPC 对话失败:", error);
      toast.error("王大达暂时没有回应");
    } finally {
      setNpcTyping(null);
    }
  }, [
    addMessage,
    inputText,
    isNpcTyping,
    selectedChar,
    sessionId,
    setNpcTyping,
  ]);

  const handleAdvance = useCallback(async () => {
    if (!sessionId) return;
    try {
      const result = await api.performAction(sessionId, "request_advance", {
        reason: "玩家请求推进",
      });
      if (result.type === "advance_denied") {
        toast(result.hint, { icon: "💡", duration: 4000 });
        return;
      }
      if (!isMockMode() && result.type === "stage_transition") {
        const session = await api.getSession(sessionId);
        setStage(session.current_stage);
        setScene(session.current_scene);
        setActions(session.available_actions as ActionType[]);
      }
    } catch (error) {
      console.error("[ChatPanel] 阶段推进失败:", error);
      toast.error("当前还不能推进", {
        description: "请检查人物章节、调查材料和证物出示是否完成。",
      });
    }
  }, [sessionId, setActions, setScene, setStage]);

  const currentCharConfig = npcConfig[selectedChar] || { name: selectedChar, color: "#fff", icon: "?" };
  const canShowAdvance = currentStage !== "epilogue" && currentStage !== "back_door_judgement";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 拖拽手柄（手机） */}
      <div className="flex justify-center py-1.5 md:hidden">
        <div className="w-10 h-1 rounded-full bg-white/20" />
      </div>

      {/* 对话列表 */}
      <div
        ref={messagesViewportRef}
        onScroll={handleMessagesScroll}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain py-2 space-y-1.5 scroll-smooth"
      >
        {chatMessages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-white/30 text-sm">
            <p className="mb-1 text-lg">💬</p>
            <p>故事即将开始……</p>
          </div>
        )}

        {chatMessages.map((msg: any) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {isNpcTyping && typingCharacterId && (
          <TypingDots charName={npcConfig[typingCharacterId]?.name || typingCharacterId} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区 */}
      <div className="shrink-0 border-t border-white/5 px-3 py-2.5 bg-gradient-to-t from-[var(--background)] via-[var(--background)]/95 to-transparent">
        {/* 快捷操作行 */}
        <div className="flex items-center gap-1.5 mb-2">
          {/* 角色选择 */}
          <div className="relative">
            <button
              onClick={() => setShowCharMenu(!showCharMenu)}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/70 hover:text-white hover:border-white/20 hover:bg-white/5 transition-all"
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: currentCharConfig.color }}
              />
              @{currentCharConfig.name}
              <ChevronUp className={`h-3 w-3 transition-transform duration-200 ${showCharMenu ? "" : "rotate-180"}`} />
            </button>

            <AnimatePresence>
              {showCharMenu && (
                <motion.div
                  initial={{ opacity: 0, y: -4, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4, scale: 0.95 }}
                  className="absolute bottom-full left-0 mb-1 flex gap-1 flex-wrap bg-[var(--panel-bg)] border border-white/10 rounded-xl p-2 shadow-2xl backdrop-blur-xl min-w-[200px]"
                >
                  {isMockMode() && (
                    <button
                      onClick={() => {
                        setSelectedChar("dm");
                        setShowCharMenu(false);
                      }}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs transition-all ${
                        selectedChar === "dm"
                          ? "bg-[var(--info)]/20 text-[var(--info)]"
                          : "text-white/60 hover:bg-white/5 hover:text-white"
                      }`}
                    >
                      🎭 DM · 叙事者
                    </button>
                  )}
                  {availableCharacters.map((c: any) => {
                    const cfg = npcConfig[c.id];
                    return (
                      <button
                        key={c.id}
                        onClick={() => { setSelectedChar(c.id); setShowCharMenu(false); }}
                        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs transition-all w-full ${
                          selectedChar === c.id
                            ? "bg-[var(--theme-primary)]/20 text-[var(--theme-primary)]"
                            : "text-white/60 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        {cfg?.icon || "?"} {cfg?.name || c.id}
                      </button>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* 快捷按钮 */}
          <button
            onClick={() => useGameStore.getState().openPanel("evidence")}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/50 hover:text-white/80 hover:border-white/20 transition-all"
          >
            [出示证物]
          </button>
          <button
            onClick={() => useGameStore.getState().openPanel("clue")}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/50 hover:text-white/80 hover:border-white/20 transition-all"
          >
            [线索板]
          </button>
        </div>

        {/* 输入框行 */}
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={`对 ${currentCharConfig.name} 说点什么……`}
              className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white outline-none transition-all placeholder:text-white/25 focus:border-[var(--theme-primary)]/50 focus:bg-white/[0.08]"
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!inputText.trim()}
            className="flex items-center justify-center rounded-xl bg-[var(--theme-primary)] px-4 text-white transition-all hover:bg-[var(--theme-primary)]/80 disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-[var(--theme-primary)]/20"
          >
            <Send className="h-4 w-4" />
          </button>
          {canShowAdvance && (
            <button
              onClick={handleAdvance}
              className="hidden sm:flex items-center gap-1 rounded-xl border border-white/10 px-3 py-2.5 text-xs text-white/50 hover:text-white/80 hover:border-white/20 transition-all"
              title="推进到下一阶段"
            >
              <Sparkles className="h-3.5 w-3.5" />
              推进
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
