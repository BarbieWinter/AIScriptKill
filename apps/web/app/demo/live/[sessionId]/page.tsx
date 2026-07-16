"use client";

import { useParams } from "next/navigation";

import { DemoGameShell } from "@/components/demo/DemoGameShell";
import { GameSessionBoundary } from "@/components/game/GameSessionBoundary";

export default function LiveDemoPage() {
  const params = useParams<{ sessionId: string }>();
  return (
    <GameSessionBoundary source="live" sessionId={params.sessionId}>
      <DemoGameShell source="live" />
    </GameSessionBoundary>
  );
}
