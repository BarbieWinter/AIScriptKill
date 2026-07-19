"use client";

import { useParams } from "next/navigation";

import { DemoGameShell } from "@/components/demo/DemoGameShell";
import { GameSessionBoundary } from "@/components/game/GameSessionBoundary";
import { isMockMode } from "@/lib/api";

export default function GameScenePage() {
  const params = useParams<{ sessionId: string; gameSessionId: string }>();
  const source = isMockMode() ? "mock" : "live";

  return (
    <GameSessionBoundary source={source} sessionId={params.gameSessionId}>
      <DemoGameShell source={source} />
    </GameSessionBoundary>
  );
}
