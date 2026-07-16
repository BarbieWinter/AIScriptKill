/**
 * GamePage — 游戏主界面
 *
 * 核心理念：不是聊天软件，是一面"会讲故事的窗户"。
 * 场景是绝对的主角，UI 元素像玻璃上的半透明贴纸。
 *
 * 布局层次（z-index 从低到高）:
 *   z-0   纯黑背景
 *   z-10  场景背景（全屏）
 *   z-15  特效层（闪光/暗角/粒子）
 *   z-20  热区交互层
 *   z-30  顶部操作栏（毛玻璃）
 *   z-35  阶段切换横幅
 *   z-40  浮动对话面板（底部，可收起）
 *   z-50  模态面板（线索/背包/推理）
 */

"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore, type ActionType } from "@/stores/gameStore";
import { api, isMockMode } from "@/lib/api";
import { WsClient } from "@/lib/ws";
import { mockScenes } from "@/lib/mock-data";
import { SceneBackground } from "@/components/game/SceneBackground";
import { SceneHotspots } from "@/components/game/SceneHotspots";
import { ChatPanel } from "@/components/game/ChatPanel";
import { ClueBoard } from "@/components/game/ClueBoard";
import { EvidenceBackpack } from "@/components/game/EvidenceBackpack";
import { CharacterChapters } from "@/components/game/CharacterChapters";
import { StageTransition } from "@/components/game/StageTransition";
import { FinalSubmission } from "@/components/game/FinalSubmission";
import { TruthReveal } from "@/components/game/TruthReveal";
import { toast } from "sonner";
import {
  Search, Backpack, BookOpen, Send, ArrowLeft,
  Menu as MenuIcon, X, Sparkles, MessageSquare,
} from "lucide-react";

/* ── NPC 名称映射（用于场景标签） ── */
const npcNames: Record<string, string> = {
  wangdada: "王大达", chengjun: "程俊",
  zhuosiyuan: "卓司元", cuikaiqiang: "崔铠强",
};

const liveSceneHotspots: Record<
  string,
  Array<{ id: string; label: string; x: number; y: number; width: number; height: number }>
> = {
  "back-alley": [
    {
      id: "back-door-traces",
      label: "🔍 后门旁的痕迹",
      x: 58,
      y: 44,
      width: 18,
      height: 18,
    },
  ],
};

export default function GamePage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  /* store */
  const setSession = useGameStore((s) => s.setSession);
  const setStage = useGameStore((s) => s.setStage);
  const setScene = useGameStore((s) => s.setScene);
  const setActions = useGameStore((s) => s.setActions);
  const setTotalCluesInRound = useGameStore((s) => s.setTotalCluesInRound);
  const setCharacters = useGameStore((s) => s.setCharacters);
  const setClues = useGameStore((s) => s.setClues);
  const setEvidences = useGameStore((s) => s.setEvidences);
  const setMessages = useGameStore((s) => s.setMessages);
  const setCards = useGameStore((s) => s.setCards);
  const currentStage = useGameStore((s) => s.currentStage);
  const currentScene = useGameStore((s) => s.currentScene);
  const addMessage = useGameStore((s) => s.addMessage);
  const addClue = useGameStore((s) => s.addClue);
  const addEvidence = useGameStore((s) => s.addEvidence);
  const openPanel = useGameStore((s) => s.openPanel);

  /* local state */
  const [flash, setFlash] = useState(false);
  const [tension, setTension] = useState(false);
  const [showFinal, setShowFinal] = useState(false);
  const [showTruth, setShowTruth] = useState(false);
  const [banner, setBanner] = useState<{ name: string; reason?: string } | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [clueToast, setClueToast] = useState<{ name: string; isKey: boolean } | null>(null);
  const [truthSummary, setTruthSummary] = useState("");

  const hydrateSession = useCallback(async () => {
    const [session, characters, clues, evidences, chat, cards] = await Promise.all([
      api.getSession(sessionId),
      api.getCharacters(sessionId),
      api.getClues(sessionId),
      api.getEvidences(sessionId),
      api.getChatHistory(sessionId),
      api.getCards(sessionId),
    ]);

    const availableCharacterIds = new Set(session.available_characters);
    const availableCharacters = characters.characters
      .filter(
        (character) =>
          character.dialogue_available &&
          (availableCharacterIds.size === 0 || availableCharacterIds.has(character.id))
      )
      .map((character) => ({
        id: character.id,
        name: character.name,
        mood: character.current_mood,
      }));

    const hydratedEvidences = evidences.evidences.map((evidence) => ({
      ...evidence,
      status: session.viewed_evidences.includes(evidence.id)
        ? "viewed"
        : evidence.status,
    }));

    setSession(session.session_id, session.script_id, session.player_character_id);
    setStage(session.current_stage);
    setScene(session.current_scene);
    setActions(session.available_actions as ActionType[]);
    setTotalCluesInRound(session.total_clues_in_round);
    setCharacters(availableCharacters);
    setClues(clues.clues);
    setEvidences(hydratedEvidences);
    setMessages(chat.messages);
    setCards(cards.cards);
  }, [
    sessionId,
    setActions,
    setCards,
    setCharacters,
    setClues,
    setEvidences,
    setMessages,
    setScene,
    setSession,
    setStage,
    setTotalCluesInRound,
  ]);

  // ══ 初始化 ══
  useEffect(() => {
    let cancelled = false;

    hydrateSession().catch((error) => {
      if (cancelled) return;
      console.error("[GamePage] 会话状态同步失败:", error);
      toast.error("无法加载游戏会话", {
        description: "请确认后端服务和剧本包已就绪。",
      });
    });

    return () => {
      cancelled = true;
    };
  }, [hydrateSession]);

  // ══ WebSocket 事件 ══
  useEffect(() => {
    let wsCleanup: (() => void) | null = null;

    if (!isMockMode()) {
      const ws = new WsClient(sessionId);
      let firstPong = true;
      const offPong = ws.on("session.pong", (data: { session_id?: string }) => {
        if (firstPong) {
          firstPong = false;
          toast.success("后端实时通道已连接", {
            description: data.session_id ? `会话 ${data.session_id}` : undefined,
            duration: 2500,
          });
        }
      });

      ws.connect();
      wsCleanup = () => {
        offPong();
        ws.disconnect();
      };
      return () => wsCleanup?.();
    }

    import("@/lib/mock-ws").then(({ MockWsClient }) => {
      const ws = new MockWsClient(sessionId);

      ws.on("chat.message", (data: any) => addMessage(data));
      ws.on("hint.shown", (data: any) => toast(data.text, { icon: "💡", duration: 6000 }));

      ws.on("clue.unlocked", (data: any) => {
        setFlash(true); setTimeout(() => setFlash(false), 400);
        addClue({ id: data.clue_id, name: data.name, description: data.description, is_key: data.is_key, importance: data.is_key ? 4 : 2, status: "discovered" });
        setClueToast({ name: data.name, isKey: data.is_key });
        setTimeout(() => setClueToast(null), 3000);
      });

      ws.on("evidence.discovered", (data: any) => {
        addEvidence({ id: data.evidence_id, name: data.name, description_surface: data.description || "", status: "discovered", can_show_to_npc: true, shown_to_characters: [] });
        toast(`📦 ${data.name}`, { description: "已加入证物背包" });
      });

      ws.on("stage.changed", (data: any) => {
        setStage(data.to);
        setActions(data.available_actions || []);
        setBanner({ name: data.stage_name, reason: data.reason });
        const sceneMap: Record<string, string> = {
          prologue: "village_entrance", act1_investigation: "restaurant_hall",
          act1_event: "crime_scene", act2_investigation: "restaurant_hall",
          act2_confrontation: "back_alley", act3_reveal: "crime_scene", epilogue: "village_entrance",
        };
        setScene(sceneMap[data.to] || "village_entrance");
        if (data.to === "act1_event" || data.to === "act2_confrontation") setTension(true);
      });
      ws.on("media.bgm_change", (data: any) => { if (data.to === "bgm_tension") setTension(true); });
      ws.connect();
      wsCleanup = () => ws.disconnect();
    });

    return () => wsCleanup?.();
  }, [addClue, addEvidence, addMessage, sessionId, setActions, setScene, setStage]);

  const currentSceneConfig = isMockMode()
    ? mockScenes.find((scene) => scene.id === currentScene)
    : null;
  const currentHotspots = isMockMode()
    ? currentSceneConfig?.hotspots ?? []
    : liveSceneHotspots[currentScene] ?? [];
  const discoveredEvidences = useGameStore((state) => state.discoveredEvidences);
  const discoveredEvidenceIds = discoveredEvidences.map((evidence) => evidence.id);
  const investigatedHotspotIds = discoveredEvidenceIds.includes("evidence-back-door-image")
    ? ["back-door-traces"]
    : [];
  const canSubmitFinal = currentStage === "back_door_judgement";

  return (
    <main className="relative h-screen w-full overflow-hidden bg-[var(--background)] select-none">
      {/* ══ Layer 0: 背景 ══ */}
      <div className="absolute inset-0 z-0 bg-[var(--background)]" />

      {/* ══ Layer 1: 场景 ══ */}
      <SceneBackground />

      {/* ══ 线索发现提示（弹出式卡片） ══ */}
      <AnimatePresence>
        {clueToast && (
          <motion.div
            initial={{ opacity: 0, y: 40, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.9 }}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 pointer-events-none"
          >
            <div className="flex flex-col items-center gap-2">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", damping: 12, delay: 0.1 }}
                className="text-4xl"
              >
                {clueToast?.isKey ? "⭐" : "🔍"}
              </motion.div>
              <div className="rounded-xl bg-black/80 backdrop-blur-md border border-white/10 px-6 py-3 text-center">
                <p className="text-xs text-white/50 mb-1">
                  {clueToast?.isKey ? "关键线索" : "发现线索"}
                </p>
                <p className="text-sm font-bold text-white">
                  {clueToast?.name}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ══ 闪光特效 ══ */}
      <AnimatePresence>
        {flash && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.5, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="absolute inset-0 z-15 bg-white pointer-events-none"
          />
        )}
      </AnimatePresence>

      {/* ══ 紧张暗角 ══ */}
      {tension && (
        <div
          className="absolute inset-0 z-15 pointer-events-none"
          style={{
            background: "radial-gradient(ellipse at center, transparent 35%, rgba(180,20,20,0.08) 100%)",
            transition: "all 2s ease",
          }}
        />
      )}

      {/* ══ Layer 2: 场景热区 ══ */}
      {currentHotspots.length > 0 && (
        <SceneHotspots
          key={`${currentScene}:${investigatedHotspotIds.join(",")}`}
          sceneId={currentScene}
          hotspots={currentHotspots}
          discovered={investigatedHotspotIds}
        />
      )}

      {/* ══ Layer 3: 顶部栏（纯透明浮动） ══ */}
      <header className="absolute left-0 right-0 top-0 z-30">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => router.push("/library")}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-black/40 backdrop-blur-sm border border-white/5 text-white/60 hover:text-white/90 hover:bg-black/60 transition-all"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          </div>
          <div className="flex items-center gap-1.5">
            <button onClick={() => openPanel("clue")}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-black/40 backdrop-blur-sm border border-white/5 text-white/60 hover:text-white/90 hover:bg-black/60 transition-all"
              title="线索板">
              <Search className="h-4 w-4" />
            </button>
            <button onClick={() => openPanel("evidence")}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-black/40 backdrop-blur-sm border border-white/5 text-white/60 hover:text-white/90 hover:bg-black/60 transition-all"
              title="证物背包">
              <Backpack className="h-4 w-4" />
            </button>
            <button onClick={() => openPanel("chapter")}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-black/40 backdrop-blur-sm border border-white/5 text-white/60 hover:text-white/90 hover:bg-black/60 transition-all"
              title="人物章节">
              <BookOpen className="h-4 w-4" />
            </button>
            {canSubmitFinal && (
              <button onClick={() => setShowFinal(true)}
                className="flex items-center gap-1.5 rounded-lg bg-[var(--theme-primary)]/80 backdrop-blur-sm px-3 h-8 text-xs font-bold text-white hover:bg-[var(--theme-primary)] transition-all shadow-lg shadow-[var(--theme-primary)]/20"
              >
                <Send className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">提交判断</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ══ Layer 4: 对话区（浮动底部） ══ */}
      <AnimatePresence>
        {chatOpen ? (
          <motion.div
            key="chat-open"
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 100, opacity: 0 }}
            className="absolute bottom-0 left-0 right-0 z-40 flex h-[40vh] min-h-0 flex-col"
          >
            {/* 毛玻璃背景 */}
            <div className="absolute inset-0 bg-gradient-to-t from-[var(--background)] via-[var(--background)]/90 to-[var(--background)]/30 backdrop-blur-md" />

            {/* 收起手柄 */}
            <div className="relative flex shrink-0 justify-center pt-1">
              <button
                onClick={() => setChatOpen(false)}
                className="w-16 h-5 flex items-center justify-center rounded-t-lg bg-white/5 hover:bg-white/10 transition-colors border border-b-0 border-white/5"
              >
                <svg className="w-5 h-5 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            <div className="relative flex min-h-0 flex-1 flex-col">
              <ChatPanel />
            </div>
          </motion.div>
        ) : (
          <motion.button
            key="chat-closed"
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 20, opacity: 0 }}
            onClick={() => setChatOpen(true)}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 rounded-full bg-[var(--background)]/80 backdrop-blur-md border border-white/10 px-5 py-2.5 text-sm text-white/70 hover:text-white hover:bg-[var(--background)] hover:border-white/20 transition-all shadow-xl"
          >
            <MessageSquare className="h-4 w-4" />
            打开对话
          </motion.button>
        )}
      </AnimatePresence>

      {/* ══ 阶段判断 ══ */}
      <FinalSubmission
        open={showFinal}
        onClose={() => setShowFinal(false)}
        onComplete={async (result) => {
          setShowFinal(false);
          try {
            const review = await api.getReview(sessionId);
            setTruthSummary(review.truth_summary);
          } catch (error) {
            console.error("[GamePage] 加载判断复盘失败:", error);
            setTruthSummary(result.detail.evidence_boundary ?? "判断已提交，复盘暂时不可用。");
          }
          setShowTruth(true);
        }}
      />

      {/* ══ 判断结果 ══ */}
      <TruthReveal
        open={showTruth}
        sessionId={sessionId}
        truthSummary={truthSummary}
      />

      {/* ══ 阶段切换横幅 ══ */}
      <StageTransition
        stageName={banner?.name ?? null}
        reason={banner?.reason}
        onComplete={() => setBanner(null)}
      />

      {/* ══ 模态面板 ══ */}
      <ClueBoard />
      <EvidenceBackpack />
      <CharacterChapters />

      {/* ══ 手机端浮动操作按钮 ══ */}
      <div className="md:hidden fixed bottom-4 right-4 z-45 flex flex-col gap-2">
        {!chatOpen && (
          <button onClick={() => setChatOpen(true)}
            className="w-12 h-12 rounded-full bg-[var(--theme-primary)] flex items-center justify-center shadow-xl shadow-[var(--theme-primary)]/30">
            <MessageSquare className="h-5 w-5 text-white" />
          </button>
        )}
        <button onClick={() => setMobileMenu(true)}
          className="w-12 h-12 rounded-full bg-black/60 backdrop-blur-md border border-white/10 flex items-center justify-center shadow-xl">
          <MenuIcon className="h-5 w-5 text-white/70" />
        </button>
      </div>

      {/* ══ 手机菜单 ══ */}
      <AnimatePresence>
        {mobileMenu && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end md:hidden"
            onClick={() => setMobileMenu(false)}
          >
            <div className="absolute inset-0 bg-black/60" />
            <motion.div
              initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              onClick={(e) => e.stopPropagation()}
              className="relative w-full rounded-t-2xl bg-[var(--panel-bg)] border-t border-white/5 p-6 pb-10"
            >
              <div className="mx-auto mb-6 w-10 h-1 rounded-full bg-white/20" />
              <div className="space-y-1">
                {[
                  { icon: Search, label: "线索板", panel: "clue" as const, color: "text-[var(--theme-primary)]" },
                  { icon: Backpack, label: "证物背包", panel: "evidence" as const, color: "text-[var(--warning)]" },
                  { icon: BookOpen, label: "人物章节", panel: "chapter" as const, color: "text-[var(--info)]" },
                ].map((item) => (
                  <button key={item.panel}
                    onClick={() => { openPanel(item.panel); setMobileMenu(false); }}
                    className="w-full flex items-center gap-3 rounded-xl px-4 py-3.5 text-sm text-white/80 hover:bg-white/5 transition-colors"
                  >
                    <item.icon className={`h-5 w-5 ${item.color}`} />
                    <span>{item.label}</span>
                  </button>
                ))}
                {canSubmitFinal && (
                  <button onClick={() => { setShowFinal(true); setMobileMenu(false); }}
                    className="w-full flex items-center gap-3 rounded-xl px-4 py-3.5 text-sm font-bold text-white bg-[var(--theme-primary)]/20 hover:bg-[var(--theme-primary)]/30 transition-colors"
                  >
                    <Send className="h-5 w-5" />
                    <span>提交判断</span>
                  </button>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
