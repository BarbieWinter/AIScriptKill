"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { GameplayPanelHost, SessionPanelDock } from "@/components/demo/GameplayPanelHost";
import { MansionDemo } from "@/components/demo/MansionDemo";
import {
  useGameSessionRuntime,
  useGameSessionStore,
} from "@/components/game/GameSessionBoundary";
import type { SessionSource } from "@/lib/game/types";
import { mapPresentationHotspots } from "@/lib/demo-world-layout";

const SessionChatDock = dynamic(
  () => import("@/components/demo/GameplayPanelHost").then((module) => module.SessionChatDock),
  { ssr: false },
);
const CharacterChapters = dynamic(
  () => import("@/components/game/CharacterChapters").then((module) => module.CharacterChapters),
  { ssr: false },
);
const ClueBoard = dynamic(
  () => import("@/components/game/ClueBoard").then((module) => module.ClueBoard),
  { ssr: false },
);
const EvidenceBackpack = dynamic(
  () => import("@/components/game/EvidenceBackpack").then((module) => module.EvidenceBackpack),
  { ssr: false },
);
const FinalSubmission = dynamic(
  () => import("@/components/game/FinalSubmission").then((module) => module.FinalSubmission),
  { ssr: false },
);

export function DemoGameShell({ source }: { source: SessionSource }) {
  const runtime = useGameSessionRuntime();
  const hydrationStatus = useGameSessionStore((state) => state.hydrationStatus);
  const hydrationError = useGameSessionStore((state) => state.hydrationError);
  const stageName = useGameSessionStore((state) => state.stageName);
  const currentScene = useGameSessionStore((state) => state.currentScene);
  const presentation = useGameSessionStore((state) => state.presentation);
  const sessionId = useGameSessionStore((state) => state.sessionId);
  const playerCharacterId = useGameSessionStore((state) => state.playerCharacterId);
  const characters = useGameSessionStore((state) => state.availableCharacters);
  const clues = useGameSessionStore((state) => state.unlockedClues);
  const evidences = useGameSessionStore((state) => state.discoveredEvidences);
  const totalClues = useGameSessionStore((state) => state.totalCluesInRound);
  const recoveryStatus = useGameSessionStore((state) => state.recoveryStatus);
  const recoveryError = useGameSessionStore((state) => state.recoveryError);

  const [panel, setPanel] = useState<"clue" | "evidence" | "chapter" | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [judgementOpen, setJudgementOpen] = useState(false);
  const [interactionPending, setInteractionPending] = useState(false);

  const scene = presentation?.scene;
  const sessionHotspots = useMemo(
    () => scene ? mapPresentationHotspots(scene.id, scene.hotspots) : [],
    [scene],
  );
  const playerName = characters.find((character) => character.id === playerCharacterId)?.name
    ?? (playerCharacterId === "zhuosiyuan" ? "卓司元" : "当前角色");
  const interactionBlocked =
    panel !== null ||
    chatOpen ||
    judgementOpen ||
    (source === "live" && recoveryStatus !== "idle");

  const investigate = async (sceneId: string, hotspotId: string) => {
    if (interactionPending) return;
    setInteractionPending(true);
    try {
      await runtime.investigate(sceneId, hotspotId);
      toast.success("调查完成", { description: "新的线索与证物已同步到游戏面板。" });
    } catch (error) {
      console.error("[DemoGameShell] 调查失败:", error);
      toast.error("当前无法调查该热点");
    } finally {
      setInteractionPending(false);
    }
  };

  if (hydrationStatus === "loading" || hydrationStatus === "idle") {
    return (
      <main className="demo-session-state">
        <div className="demo-session-loader" />
        <strong>正在恢复游戏会话</strong>
        <span>同步 YAML 剧情、线索、证物与人物章节…</span>
      </main>
    );
  }

  if (hydrationStatus === "error") {
    return (
      <main className="demo-session-state">
        <strong>无法加载这个游戏会话</strong>
        <span>{hydrationError ?? "请确认后端与剧本包已经就绪。"}</span>
        <button type="button" onClick={() => void runtime.refreshAll()}>重新加载</button>
      </main>
    );
  }

  return (
    <MansionDemo
      sessionHotspots={sessionHotspots}
      interactionBlocked={interactionBlocked}
      interactionPending={interactionPending}
      onInvestigate={investigate}
      stageName={stageName || presentation?.stage.name}
      statusLabel={source === "mock" ? "Mock 会话 · 刷新会重置" : "Live 会话 · YAML / LangGraph"}
      overlay={
        <GameplayPanelHost>
          {source === "mock" && (
            <div className="demo-mock-warning">MOCK DATA · 浏览器刷新会重置进度</div>
          )}
          {!scene && (
            <div className="demo-presentation-warning">
              当前场景 {currentScene || "未知"} 尚未提供可公开的地图热点投影。
            </div>
          )}
          {source === "live" && recoveryStatus !== "idle" && (
            <div
              data-testid="recovery-status"
              className="absolute left-1/2 top-4 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-full border border-white/10 bg-black/75 px-4 py-2 text-xs text-white/75 backdrop-blur-md"
            >
              <span>
                {recoveryStatus === "uncertain"
                  ? "上次操作结果待确认"
                  : recoveryStatus === "conflict"
                    ? "状态已变化，正在同步"
                    : recoveryStatus === "error"
                      ? "同步权威状态失败"
                      : "正在同步权威状态"}
              </span>
              {(recoveryStatus === "uncertain" || recoveryStatus === "error") && (
                <button
                  type="button"
                  data-testid="recovery-retry"
                  onClick={() => void runtime.retryPendingCommand().catch(() => undefined)}
                  className="font-medium text-[var(--theme-primary)] hover:text-white"
                  title={recoveryError ?? undefined}
                >
                  重新确认
                </button>
              )}
            </div>
          )}
          <SessionPanelDock
            onOpenClues={() => setPanel("clue")}
            onOpenEvidence={() => setPanel("evidence")}
            onOpenChapters={() => setPanel("chapter")}
            onOpenChat={() => setChatOpen(true)}
            onOpenJudgement={presentation?.judgement ? () => setJudgementOpen(true) : undefined}
            disabled={source === "live" && recoveryStatus !== "idle"}
          />
          {chatOpen && <SessionChatDock open onClose={() => setChatOpen(false)} />}
          {panel === "clue" && <ClueBoard
            open
            onClose={() => setPanel(null)}
            clues={clues}
            totalCluesInRound={totalClues}
          />}
          {panel === "evidence" && <EvidenceBackpack
            open
            onClose={() => setPanel(null)}
            sessionId={sessionId}
            playerCharacterId={playerCharacterId}
            evidences={evidences}
            characters={characters}
            onViewEvidence={(evidenceId) => runtime.viewEvidence(evidenceId)}
            onShowEvidence={(characterId, evidenceId) => runtime.showEvidence(characterId, evidenceId)}
          />}
          {panel === "chapter" && <CharacterChapters
            open
            onClose={() => setPanel(null)}
            sessionId={sessionId}
            playerCharacterName={playerName}
            onListChapters={() => runtime.listCharacterChapters()}
            onReadChapter={(chapterId) => runtime.readCharacterChapter(chapterId)}
          />}
          {judgementOpen && <FinalSubmission
            open
            onClose={() => setJudgementOpen(false)}
            judgement={presentation?.judgement}
            onSubmit={(optionId) => runtime.submitJudgment(optionId)}
            onComplete={() => setJudgementOpen(false)}
          />}
        </GameplayPanelHost>
      }
    />
  );
}
