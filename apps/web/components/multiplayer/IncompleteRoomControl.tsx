"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleStop, LoaderCircle, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  multiplayerErrorCode,
  multiplayerErrorMessage,
} from "@/lib/multiplayer/error-messages";
import {
  currentMultiplayerRoomKey,
  roomSnapshotKey,
  type MultiplayerRoomClient,
} from "@/lib/multiplayer/room-client";
import type {
  GameplaySnapshotV1,
  LobbySnapshotV1,
} from "@/lib/multiplayer/types";

type IncompleteRoomSnapshot = LobbySnapshotV1 | GameplaySnapshotV1;

type IncompleteRoomControlProps = {
  client: MultiplayerRoomClient;
  snapshot: IncompleteRoomSnapshot;
};

export function IncompleteRoomControl({ client, snapshot }: IncompleteRoomControlProps) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const triggerButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const closePendingRef = useRef(false);
  const canEnd = snapshot.status === "lobby"
    ? snapshot.capabilities.can_end_incomplete
    : snapshot.status === "active" && snapshot.can_end_incomplete;
  const actionLabel = snapshot.status === "lobby" ? "关闭房间" : "放弃本局";
  const confirmationTitle = snapshot.status === "lobby" ? "关闭这个房间？" : "放弃这局游戏？";

  const closeRoom = useMutation({
    mutationFn: () => client.sendCommand(snapshot.session_id, {
      expected_revision: snapshot.revision,
      type: "room.end_incomplete",
      payload: { reason: null },
    }),
    onSuccess: async () => {
      setConfirming(false);
      queryClient.setQueryData(currentMultiplayerRoomKey, null);
      await queryClient.invalidateQueries({ queryKey: roomSnapshotKey(snapshot.session_id) });
    },
  });
  closePendingRef.current = closeRoom.isPending;

  useEffect(() => {
    if (!confirming) return;
    const triggerButton = triggerButtonRef.current;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : triggerButton;
    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => confirmButtonRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (event.key === "Escape") {
        if (closePendingRef.current) return;
        event.preventDefault();
        setConfirming(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const activeIndex = focusable.indexOf(document.activeElement as HTMLElement);
      if (activeIndex < 0) {
        event.preventDefault();
        (event.shiftKey ? focusable.at(-1) : focusable[0])?.focus();
      } else if (event.shiftKey && activeIndex === 0) {
        event.preventDefault();
        focusable.at(-1)?.focus();
      } else if (!event.shiftKey && activeIndex === focusable.length - 1) {
        event.preventDefault();
        focusable[0]?.focus();
      }
    };
    const containFocus = (event: FocusEvent) => {
      const dialog = dialogRef.current;
      if (!dialog || !(event.target instanceof HTMLElement) || dialog.contains(event.target)) return;
      (confirmButtonRef.current ?? dialog).focus();
    };
    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("focusin", containFocus, true);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown, true);
      document.removeEventListener("focusin", containFocus, true);
      document.body.style.overflow = previousBodyOverflow;
      window.requestAnimationFrame(() => {
        const focusTarget = previousFocus?.isConnected ? previousFocus : triggerButton;
        if (focusTarget?.isConnected && !focusTarget.matches(":disabled")) {
          focusTarget.focus();
          return;
        }
        const fallback = document.querySelector<HTMLElement>('main, [role="main"]');
        if (fallback) {
          if (!fallback.hasAttribute("tabindex")) fallback.tabIndex = -1;
          fallback.focus();
        }
      });
    };
  }, [confirming]);

  if (!canEnd) return null;

  return (
    <>
      <button
        ref={triggerButtonRef}
        type="button"
        onClick={() => {
          closeRoom.reset();
          setConfirming(true);
        }}
        className="fixed right-4 bottom-4 z-40 inline-flex h-10 items-center gap-2 rounded-lg border border-red-200/20 bg-[#171312]/95 px-3 text-xs font-medium text-red-100 shadow-xl backdrop-blur hover:border-red-200/35 hover:bg-[#211716] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-200 md:right-6 md:bottom-6"
      >
        <CircleStop className="h-4 w-4" />
        {actionLabel}
      </button>

      {confirming && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 px-4 backdrop-blur-sm"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !closeRoom.isPending) setConfirming(false);
          }}
        >
          <section
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="incomplete-room-title"
            tabIndex={-1}
            className="w-full max-w-md rounded-lg border border-red-200/15 bg-[#111412] p-6 text-[#e8e2d5] shadow-2xl"
          >
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 id="incomplete-room-title" className="text-lg font-semibold">
                  {confirmationTitle}
                </h2>
                <p className="mt-2 text-sm leading-6 text-[#aeb1ab]">
                  房间会立即结束，双方将离开当前占用。本局不会生成结局或复盘。
                </p>
              </div>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={closeRoom.isPending}
                aria-label="取消关闭"
                title="取消关闭"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#9fa29c] hover:bg-white/5 hover:text-white disabled:opacity-40"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {closeRoom.isError && (
              <div role="alert" className="mb-4 rounded-md border border-red-300/15 bg-red-300/[0.06] px-3 py-2 text-sm text-red-100">
                <p>{multiplayerErrorMessage(closeRoom.error)}</p>
                {multiplayerErrorCode(closeRoom.error) && (
                  <p className="mt-1 font-mono text-[11px] text-red-200/60">
                    {multiplayerErrorCode(closeRoom.error)}
                  </p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={closeRoom.isPending}
                className="rounded-lg border border-white/10 px-4 py-2 text-sm text-[#d0d2cc] hover:bg-white/5 disabled:opacity-40"
              >
                返回
              </button>
              <button
                ref={confirmButtonRef}
                type="button"
                onClick={() => closeRoom.mutate()}
                disabled={closeRoom.isPending}
                className="inline-flex min-w-28 items-center justify-center gap-2 rounded-lg bg-[#a4403b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#b84a44] disabled:opacity-50"
              >
                {closeRoom.isPending && <LoaderCircle className="h-4 w-4 animate-spin" />}
                确认{actionLabel}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
