"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";

import { GameplayPanelHost, SessionChatDock, SessionPanelDock } from "@/components/demo/GameplayPanelHost";
import { MansionDemo } from "@/components/demo/MansionDemo";
import { CharacterChapters } from "@/components/game/CharacterChapters";
import { ClueBoard } from "@/components/game/ClueBoard";
import { EvidenceBackpack } from "@/components/game/EvidenceBackpack";
import { FinalSubmission } from "@/components/game/FinalSubmission";
import {
  useGameSessionRuntime,
  useGameSessionStore,
} from "@/components/game/GameSessionBoundary";
import type { SessionSource } from "@/lib/game/types";
import { mapPresentationHotspots } from "@/lib/demo-world-layout";

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
  const interactionBlocked = panel !== null || chatOpen || judgementOpen;

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
          <SessionPanelDock
            onOpenClues={() => setPanel("clue")}
            onOpenEvidence={() => setPanel("evidence")}
            onOpenChapters={() => setPanel("chapter")}
            onOpenChat={() => setChatOpen(true)}
            onOpenJudgement={presentation?.judgement ? () => setJudgementOpen(true) : undefined}
          />
          <SessionChatDock open={chatOpen} onClose={() => setChatOpen(false)} />
          <ClueBoard
            open={panel === "clue"}
            onClose={() => setPanel(null)}
            clues={clues}
            totalCluesInRound={totalClues}
          />
          <EvidenceBackpack
            open={panel === "evidence"}
            onClose={() => setPanel(null)}
            sessionId={sessionId}
            playerCharacterId={playerCharacterId}
            evidences={evidences}
            characters={characters}
            onViewEvidence={(evidenceId) => runtime.viewEvidence(evidenceId)}
            onShowEvidence={(characterId, evidenceId) => runtime.showEvidence(characterId, evidenceId)}
          />
          <CharacterChapters
            open={panel === "chapter"}
            onClose={() => setPanel(null)}
            sessionId={sessionId}
            playerCharacterName={playerName}
            onListChapters={() => runtime.listCharacterChapters()}
            onReadChapter={(chapterId) => runtime.readCharacterChapter(chapterId)}
          />
          <FinalSubmission
            open={judgementOpen}
            onClose={() => setJudgementOpen(false)}
            judgement={presentation?.judgement}
            onSubmit={(optionId) => runtime.submitJudgment(optionId)}
            onComplete={() => setJudgementOpen(false)}
          />
        </GameplayPanelHost>
      }
    />
  );
}
