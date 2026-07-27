"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, DoorClosed, LoaderCircle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import {
  createMultiplayerRoomClient,
  roomSnapshotKey,
} from "@/lib/multiplayer/room-client";
import { IncompleteRoomControl } from "./IncompleteRoomControl";
import { LobbyShell } from "./LobbyShell";
import { MultiplayerMansionShell } from "./MultiplayerMansionShell";

export function LobbyBoundary({ sessionId }: { sessionId: string }) {
  const client = useMemo(() => createMultiplayerRoomClient(), []);
  const snapshot = useQuery({
    queryKey: roomSnapshotKey(sessionId),
    queryFn: ({ signal }) => client.getSnapshot(sessionId, signal),
    retry: shouldRetryMultiplayer,
    refetchInterval: (query) => query.state.data?.status === "closed" ? false : 2_000,
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

  if (!snapshot.data) {
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

  const syncWarning = snapshot.isError ? (
    <div role="alert" className="fixed inset-x-4 top-4 z-50 mx-auto flex max-w-xl items-center justify-between gap-3 rounded-xl border border-amber-200/25 bg-[#211b10]/95 px-4 py-3 text-sm text-amber-50 shadow-2xl backdrop-blur">
      <div className="flex items-center gap-2">
        <CircleAlert className="h-4 w-4 shrink-0 text-amber-200" />
        <span>同步暂时中断，正在显示上次成功状态。</span>
      </div>
      <button
        type="button"
        onClick={() => snapshot.refetch()}
        disabled={snapshot.isFetching}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-amber-100/20 px-3 py-1.5 text-xs disabled:opacity-50"
      >
        <RotateCcw className={`h-3.5 w-3.5 ${snapshot.isFetching ? "animate-spin" : ""}`} />
        重试同步
      </button>
    </div>
  ) : null;

  if (snapshot.data.status === "closed") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#080a0c] px-5 text-[#e8e2d5]">
        {syncWarning}
        <section className="w-full max-w-lg text-center">
          <DoorClosed className="mx-auto mb-5 h-9 w-9 text-[#c9ae76]" />
          <h1 className="text-2xl font-semibold">房间已关闭</h1>
          <p className="mt-3 text-sm leading-6 text-[#aeb1ab]">
            {snapshot.data.package.title} 未完成结束，因此没有结局或复盘。当前身份已可创建或加入其他房间。
          </p>
          <Link
            href="/multiplayer"
            className="mt-7 inline-flex rounded-lg bg-[#c6a867] px-5 py-2.5 text-sm font-semibold text-[#11120f] hover:bg-[#d2b879]"
          >
            返回多人入口
          </Link>
        </section>
      </main>
    );
  }

  const room = snapshot.data.status === "lobby"
    ? <LobbyShell client={client} snapshot={snapshot.data} />
    : <MultiplayerMansionShell client={client} snapshot={snapshot.data} />;
  return (
    <>
      {syncWarning}
      {room}
      <IncompleteRoomControl client={client} snapshot={snapshot.data} />
    </>
  );
}
