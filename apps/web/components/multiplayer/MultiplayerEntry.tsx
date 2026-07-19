"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, LoaderCircle, RotateCcw, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo } from "react";

import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
  shouldRetryMultiplayer,
} from "@/lib/multiplayer/error-messages";
import {
  createMultiplayerRoomClient,
  MultiplayerClientError,
} from "@/lib/multiplayer/room-client";

const SCRIPT_ID = "mp1-two-player";
const currentRoomKey = ["multiplayer", "current-room"] as const;

export function MultiplayerEntry() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const client = useMemo(() => createMultiplayerRoomClient(), []);
  const currentRoom = useQuery({
    queryKey: currentRoomKey,
    queryFn: ({ signal }) => client.getCurrentRoom(signal),
    retry: shouldRetryMultiplayer,
    refetchOnWindowFocus: true,
  });
  const createRoom = useMutation({
    mutationFn: () => client.createRoom(SCRIPT_ID),
    onSuccess: (room) => {
      queryClient.setQueryData(currentRoomKey, room);
      router.push(`/play/${encodeURIComponent(room.session_id)}/lobby`);
    },
    onError: (error) => {
      if (
        error instanceof MultiplayerClientError &&
        error.code === "UNFINISHED_ROOM_EXISTS" &&
        error.details.session_id
      ) {
        router.push(`/play/${encodeURIComponent(error.details.session_id)}/lobby`);
      }
    },
  });

  const error = createRoom.error ?? currentRoom.error;
  const errorCode = multiplayerErrorCode(error);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#080a0c] px-5 py-12 text-[#e8e2d5]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(167,139,86,0.16),transparent_42%)]" />
      <div className="relative mx-auto flex min-h-[calc(100vh-6rem)] max-w-2xl items-center">
        <section className="w-full rounded-3xl border border-[#b89a61]/20 bg-[#111412]/95 p-7 shadow-2xl shadow-black/40 md:p-10">
          <div className="mb-8 flex h-12 w-12 items-center justify-center rounded-2xl border border-[#b89a61]/25 bg-[#b89a61]/10">
            <Users className="h-6 w-6 text-[#c9ae76]" />
          </div>
          <p className="mb-3 text-xs tracking-[0.28em] text-[#a98e5d] uppercase">Multiplayer v1</p>
          <h1 className="mb-3 text-3xl font-semibold tracking-tight md:text-4xl">双人剧本房间</h1>
          <p className="mb-9 max-w-xl text-sm leading-7 text-[#a9aaa3]">
            浏览器会安全保存匿名玩家身份。创建房间后邀请一位朋友，双方选角并准备即可开始。
          </p>

          {currentRoom.isPending ? (
            <div className="flex items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.025] p-5 text-sm text-[#b9bbb5]">
              <LoaderCircle className="h-5 w-5 animate-spin" />
              正在恢复匿名会话…
            </div>
          ) : currentRoom.data ? (
            <div className="rounded-2xl border border-[#b89a61]/25 bg-[#b89a61]/[0.06] p-5">
              <p className="mb-1 text-sm font-medium">发现未结束的房间</p>
              <p className="mb-5 text-xs text-[#92958f]">
                状态：{currentRoom.data.status === "lobby" ? "等待中" : "已开始"}
              </p>
              <button
                type="button"
                onClick={() => router.push(`/play/${encodeURIComponent(currentRoom.data!.session_id)}/lobby`)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3 text-sm font-semibold text-[#11120f] transition hover:bg-[#d6ba78]"
              >
                继续房间
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => createRoom.mutate()}
              disabled={createRoom.isPending || currentRoom.isError}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#c6a867] px-5 py-3.5 text-sm font-semibold text-[#11120f] transition hover:bg-[#d6ba78] disabled:cursor-not-allowed disabled:opacity-45"
            >
              {createRoom.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Users className="h-4 w-4" />}
              {createRoom.isPending ? "正在创建…" : "创建双人房间"}
            </button>
          )}

          {Boolean(error) && (
            <div role="alert" className="mt-5 rounded-xl border border-red-400/20 bg-red-400/[0.07] p-4 text-sm text-red-100">
              <p>{multiplayerErrorMessage(error)}</p>
              {errorCode && <p className="mt-1 font-mono text-[11px] text-red-200/55">{errorCode}</p>}
              {currentRoom.isError && (
                <button
                  type="button"
                  onClick={() => currentRoom.refetch()}
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-red-100 underline underline-offset-4"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  重试
                </button>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
