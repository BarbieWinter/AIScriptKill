"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, LoaderCircle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import {
  createMultiplayerRoomClient,
  lobbySnapshotKey,
} from "@/lib/multiplayer/room-client";
import { LobbyShell } from "./LobbyShell";

export function LobbyBoundary({ sessionId }: { sessionId: string }) {
  const client = useMemo(() => createMultiplayerRoomClient(), []);
  const snapshot = useQuery({
    queryKey: lobbySnapshotKey(sessionId),
    queryFn: ({ signal }) => client.getSnapshot(sessionId, signal),
    retry: shouldRetryMultiplayer,
    refetchInterval: (query) => query.state.data?.status === "lobby" ? 2_000 : false,
    refetchOnWindowFocus: true,
  });

  if (snapshot.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#080a0c] text-[#e8e2d5]">
        <div className="text-center">
          <LoaderCircle className="mx-auto mb-4 h-8 w-8 animate-spin text-[#c9ae76]" />
          <p className="text-sm text-[#9fa29c]">正在同步房间状态…</p>
        </div>
      </main>
    );
  }

  if (snapshot.isError || !snapshot.data) {
    const code = multiplayerErrorCode(snapshot.error);
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#080a0c] px-5 text-[#e8e2d5]">
        <section className="w-full max-w-md rounded-3xl border border-red-300/15 bg-[#111412] p-8 text-center">
          <CircleAlert className="mx-auto mb-5 h-8 w-8 text-red-300" />
          <h1 className="mb-2 text-xl font-semibold">无法读取房间</h1>
          <div role="alert" className="mb-6 text-sm leading-6 text-[#b8bab4]">
            <p>{multiplayerErrorMessage(snapshot.error)}</p>
            {code && <p className="mt-2 font-mono text-[11px] text-red-200/60">{code}</p>}
          </div>
          <button
            type="button"
            onClick={() => snapshot.refetch()}
            className="mb-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f]"
          >
            <RotateCcw className="h-4 w-4" />
            重试
          </button>
          <Link href="/multiplayer" className="text-sm text-[#9fa29c] hover:text-white">
            返回多人入口
          </Link>
        </section>
      </main>
    );
  }

  return <LobbyShell client={client} snapshot={snapshot.data} />;
}
