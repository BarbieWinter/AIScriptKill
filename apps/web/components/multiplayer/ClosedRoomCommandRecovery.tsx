"use client";

import { LoaderCircle, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  clearPersistedRoomCommand,
  pendingRoomCommandStorageKey,
  persistedRoomCommandId,
  readPersistedRoomCommand,
  resumePersistedRoomCommand,
  withCommandRecoveryRequestDeadline,
  type PersistedRoomCommand,
  type RoomCommandTerminal,
} from "@/lib/multiplayer/command-recovery";
import { multiplayerErrorMessage } from "@/lib/multiplayer/error-messages";
import { MultiplayerClientError, type MultiplayerRoomClient } from "@/lib/multiplayer/room-client";
import type { ClosedRoomSnapshotV1, RoomSnapshotV1 } from "@/lib/multiplayer/types";

type RecoveryView =
  | { status: "idle" }
  | { status: "processing"; commandId: string; error: unknown | null }
  | { status: "accepted"; commandId: string; error: unknown | null }
  | { status: "rejected"; commandId: string; error: unknown; retryable: boolean }
  | { status: "error"; commandId: string; error: unknown };

function snapshotIncludesAcceptedCommand(
  snapshot: RoomSnapshotV1,
  revision: number,
  eventSequence: number,
) {
  if (snapshot.revision < revision) return false;
  return eventSequence === 0
    || ("event_head_sequence" in snapshot && snapshot.event_head_sequence >= eventSequence);
}

export function ClosedRoomCommandRecovery({
  client,
  snapshot,
}: {
  client: MultiplayerRoomClient;
  snapshot: ClosedRoomSnapshotV1;
}) {
  const [view, setView] = useState<RecoveryView>({ status: "idle" });
  const operationRef = useRef<Promise<void> | null>(null);
  const recoveryControllerRef = useRef<AbortController | null>(null);
  const runRef = useRef<(record: PersistedRoomCommand) => void>(() => undefined);
  const generationRef = useRef(0);
  const snapshotRef = useRef<ClosedRoomSnapshotV1>(snapshot);
  snapshotRef.current = snapshot;
  const identity = `${snapshot.session_id}:${snapshot.self_member_id}`;
  const identityRef = useRef(identity);
  identityRef.current = identity;

  useLayoutEffect(() => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setView({ status: "idle" });
    return () => {
      if (generationRef.current !== generation) return;
      generationRef.current += 1;
      recoveryControllerRef.current?.abort();
      recoveryControllerRef.current = null;
      operationRef.current = null;
    };
  }, [identity]);

  const isCurrent = useCallback((record: PersistedRoomCommand, generation: number) => (
    generationRef.current === generation
    && identityRef.current === `${record.session_id}:${record.member_id}`
  ), []);

  const run = useCallback((record: PersistedRoomCommand) => {
    if (operationRef.current) return;
    const generation = generationRef.current;
    const recoveryController = new AbortController();
    recoveryControllerRef.current = recoveryController;
    const commandId = persistedRoomCommandId(record);
    let acceptedCommandId: string | null = null;
    setView({ status: "processing", commandId, error: null });
    const onProcessing = (nextCommandId: string) => {
      if (isCurrent(record, generation)) setView({ status: "processing", commandId: nextCommandId, error: null });
    };
    const operation = resumePersistedRoomCommand(
      client,
      record,
      onProcessing,
      recoveryController.signal,
    ).then(async (terminal: RoomCommandTerminal) => {
        if (!isCurrent(record, generation)) return;
        if (terminal.status === "accepted") {
          acceptedCommandId = terminal.response.command_id;
          setView({ status: "accepted", commandId: acceptedCommandId, error: null });
          if (!snapshotIncludesAcceptedCommand(
            snapshotRef.current,
            terminal.response.revision,
            terminal.response.event_sequence,
          )) {
            const fresh = await withCommandRecoveryRequestDeadline(
              (requestSignal) => client.getSnapshot(record.session_id, requestSignal),
              recoveryController.signal,
            );
            if (fresh.status !== "closed" || !snapshotIncludesAcceptedCommand(
              fresh,
              terminal.response.revision,
              terminal.response.event_sequence,
            )) {
              throw new MultiplayerClientError(
                409,
                "COMMAND_SNAPSHOT_STALE",
                "房间已关闭，但权威终态尚未覆盖已接受命令。",
              );
            }
          }
        }
        const cleared = await clearPersistedRoomCommand(
          record,
          recoveryController.signal,
        );
        if (!isCurrent(record, generation)) return;
        const remaining = readPersistedRoomCommand(record.session_id, record.member_id);
        if (!cleared && remaining?.serialized_envelope === record.serialized_envelope) {
          const storageError = new MultiplayerClientError(
            409,
            "COMMAND_STORAGE_BUSY",
            "终态已确认，但浏览器存储仍在同步，请刷新后重试。",
          );
          setView(terminal.status === "accepted"
            ? { status: "accepted", commandId, error: storageError }
            : { status: "rejected", commandId, error: storageError, retryable: true });
          return;
        }
        if (terminal.status === "rejected") {
          setView({ status: "rejected", commandId, error: terminal.error, retryable: false });
        } else {
          setView({ status: "idle" });
        }
      })
      .catch((error: unknown) => {
        if (isCurrent(record, generation) && !recoveryController.signal.aborted) {
          setView(acceptedCommandId
            ? { status: "accepted", commandId: acceptedCommandId, error }
            : { status: "processing", commandId, error });
        }
      })
      .finally(() => {
        if (operationRef.current !== operation) return;
        operationRef.current = null;
        if (recoveryControllerRef.current === recoveryController) {
          recoveryControllerRef.current = null;
        }
        const successor = readPersistedRoomCommand(record.session_id, record.member_id);
        if (
          successor
          && successor.serialized_envelope !== record.serialized_envelope
          && isCurrent(record, generation)
        ) {
          window.setTimeout(() => runRef.current(successor), 0);
        }
      });
    operationRef.current = operation;
  }, [client, isCurrent]);
  runRef.current = run;

  useEffect(() => {
    const record = readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
    if (record) run(record);
    const storageKey = pendingRoomCommandStorageKey(snapshot.session_id, snapshot.self_member_id);
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== storageKey) return;
      if (event.newValue === null) {
        recoveryControllerRef.current?.abort();
        recoveryControllerRef.current = null;
        operationRef.current = null;
        setView({ status: "idle" });
        return;
      }
      const next = readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
      if (next) run(next);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [run, snapshot.self_member_id, snapshot.session_id]);

  if (view.status === "idle") return null;
  const hasError = view.error !== null && view.error !== undefined;
  const statusText = view.status === "processing"
    ? hasError
      ? `命令状态仍不确定：${multiplayerErrorMessage(view.error)}`
      : "房间已关闭，正在确认上一条命令。"
    : view.status === "accepted"
      ? hasError
        ? `命令已接受，但终态同步失败：${multiplayerErrorMessage(view.error)}`
        : "命令已接受，正在确认关闭终态。"
      : view.status === "rejected"
        ? `命令已拒绝：${multiplayerErrorMessage(view.error)}`
        : `命令未提交：${multiplayerErrorMessage(view.error)}`;
  const retryable = view.status === "error"
    || (hasError && view.status !== "rejected")
    || (view.status === "rejected" && view.retryable);
  const alerting = hasError || view.status === "rejected" || view.status === "error";

  return (
    <div
      role={alerting ? "alert" : "status"}
      data-testid="command-recovery-status"
      className="mx-auto mt-7 flex max-w-lg items-center justify-center gap-2 rounded-lg border border-[#c9ae76]/25 bg-[#c9ae76]/[0.08] px-4 py-3 text-sm text-[#e3d8bd]"
    >
      {view.status === "processing" && !hasError
        ? <LoaderCircle className="h-4 w-4 animate-spin" />
        : <RotateCcw className="h-4 w-4" />}
      <span>{statusText}</span>
      {retryable && (
        <button
          type="button"
          onClick={() => {
            const record = readPersistedRoomCommand(snapshot.session_id, snapshot.self_member_id);
            if (record) run(record);
          }}
          className="inline-flex shrink-0 items-center gap-1 underline underline-offset-2"
        >
          <RotateCcw className="h-3.5 w-3.5" />重试
        </button>
      )}
    </div>
  );
}
