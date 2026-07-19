"use client";

import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, MessageSquare, Search, Send, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import {
  useGameSessionRuntime,
  useGameSessionStore,
} from "@/components/game/GameSessionBoundary";
import type { ChatMessage, AvailableCharacter } from "@/lib/game/types";

const palette = ["#b99b5f", "#77918d", "#96716b", "#8b859d", "#7d8a68"];

function characterColor(id: string, characters: AvailableCharacter[]) {
  const index = Math.max(0, characters.findIndex((character) => character.id === id));
  return palette[index % palette.length];
}

function speakerName(message: ChatMessage, characters: AvailableCharacter[]) {
  if (message.role === "player") return "你";
  if (message.character_id === "dm") return "叙事者";
  return characters.find((character) => character.id === message.character_id)?.name
    ?? message.character_id
    ?? "未知角色";
}

export function GameplayPanelHost({ children }: { children: ReactNode }) {
  return <div className="demo-gameplay-host">{children}</div>;
}

export function SessionChatDock({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const runtime = useGameSessionRuntime();
  const messages = useGameSessionStore((state) => state.chatMessages);
  const characters = useGameSessionStore((state) => state.availableCharacters);
  const currentStage = useGameSessionStore((state) => state.currentStage);
  const [selectedCharacterId, setSelectedCharacterId] = useState("");
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (characters.some((character) => character.id === selectedCharacterId)) return;
    setSelectedCharacterId(characters[0]?.id ?? "");
  }, [characters, selectedCharacterId]);

  useEffect(() => {
    if (!open) return;
    viewportRef.current?.scrollTo({ top: viewportRef.current.scrollHeight });
  }, [messages, open]);

  const selectedCharacter = useMemo(
    () => characters.find((character) => character.id === selectedCharacterId),
    [characters, selectedCharacterId],
  );

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || !selectedCharacterId || pending) return;
    setPending(true);
    setInput("");
    try {
      await runtime.talk(selectedCharacterId, text);
    } catch (error) {
      console.error("[SessionChatDock] 对话失败:", error);
      setInput(text);
      toast.error(`${selectedCharacter?.name ?? "角色"}暂时没有回应`);
    } finally {
      setPending(false);
    }
  };

  const advance = async () => {
    if (pending) return;
    setPending(true);
    try {
      const result = await runtime.advance("玩家从精致地图请求推进");
      if (result.type === "advance_denied") {
        toast(result.hint, { icon: "💡" });
      } else {
        toast.success("剧情阶段已更新");
      }
    } catch (error) {
      console.error("[SessionChatDock] 推进失败:", error);
      toast.error("当前还不能推进", {
        description: "请检查人物章节、调查材料与证物出示是否完成。",
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.section
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 28 }}
          className="demo-session-chat"
          aria-label="剧情对话"
        >
          <header>
            <div>
              <span>SESSION DIALOGUE</span>
              <strong>{selectedCharacter ? `与 ${selectedCharacter.name} 对话` : "当前没有可对话角色"}</strong>
            </div>
            <button type="button" onClick={onClose} aria-label="关闭对话"><X /></button>
          </header>

          <div className="demo-session-chat-messages" ref={viewportRef}>
            {messages.length === 0 ? (
              <p className="demo-session-empty">剧情记录为空。选择当前可用角色开始交谈。</p>
            ) : messages.map((message) => {
              const player = message.role === "player";
              return (
                <article key={message.id} className={player ? "is-player" : ""}>
                  <span style={{ color: characterColor(message.character_id ?? "player", characters) }}>
                    {speakerName(message, characters)}
                  </span>
                  <p>{message.text}</p>
                </article>
              );
            })}
          </div>

          <div className="demo-session-chat-controls">
            <select
              value={selectedCharacterId}
              onChange={(event) => setSelectedCharacterId(event.target.value)}
              disabled={pending || characters.length === 0}
              aria-label="选择对话角色"
            >
              {characters.map((character) => (
                <option key={character.id} value={character.id}>{character.name}</option>
              ))}
            </select>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder={selectedCharacter ? `对 ${selectedCharacter.name} 说…` : "当前没有可对话角色"}
              disabled={pending || !selectedCharacter}
              data-testid="chat-input"
            />
            <button
              type="button"
              onClick={() => void sendMessage()}
              disabled={pending || !input.trim()}
              aria-label="发送消息"
              data-testid="chat-send"
            ><Send /></button>
            {currentStage !== "back_door_judgement" && (
              <button type="button" className="demo-session-advance" onClick={() => void advance()} disabled={pending}>
                推进
              </button>
            )}
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}

export function SessionPanelDock({
  onOpenClues,
  onOpenEvidence,
  onOpenChapters,
  onOpenChat,
  onOpenJudgement,
  disabled = false,
}: {
  onOpenClues: () => void;
  onOpenEvidence: () => void;
  onOpenChapters: () => void;
  onOpenChat: () => void;
  onOpenJudgement?: () => void;
  disabled?: boolean;
}) {
  const clueCount = useGameSessionStore((state) => state.unlockedClues.length);
  const evidenceCount = useGameSessionStore((state) => state.discoveredEvidences.length);

  return (
    <nav className="demo-session-dock" aria-label="游戏数据面板">
      <button type="button" onClick={onOpenClues} disabled={disabled}><Search /><span>线索板</span><b>{clueCount}</b></button>
      <button type="button" onClick={onOpenEvidence} disabled={disabled}><span className="demo-dock-backpack">⌑</span><span>证物背包</span><b>{evidenceCount}</b></button>
      <button type="button" onClick={onOpenChapters} disabled={disabled}><BookOpen /><span>人物章节</span></button>
      <button type="button" onClick={onOpenChat} disabled={disabled} data-testid="chat-open"><MessageSquare /><span>剧情对话</span></button>
      {onOpenJudgement && <button type="button" className="is-primary" onClick={onOpenJudgement} disabled={disabled}><Send /><span>提交判断</span></button>}
    </nav>
  );
}
