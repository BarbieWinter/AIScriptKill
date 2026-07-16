"use client";

import { useParams } from "next/navigation";

import { DemoGameShell } from "@/components/demo/DemoGameShell";
import { GameSessionBoundary } from "@/components/game/GameSessionBoundary";

export default function MockDemoPage() {
  const params = useParams<{ sessionId: string }>();
  return (
    <GameSessionBoundary source="mock" sessionId={params.sessionId}>
      <DemoGameShell source="mock" />
    </GameSessionBoundary>
  );
}
