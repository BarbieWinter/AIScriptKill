"use client";

import { useParams } from "next/navigation";

import { LobbyBoundary } from "@/components/multiplayer/LobbyBoundary";

export default function MultiplayerLobbyPage() {
  const params = useParams<{ sessionId: string }>();
  return <LobbyBoundary sessionId={params.sessionId} />;
}
