import { createUuid } from "@/lib/uuid";
import { MultiplayerClientError, type MultiplayerRoomClient } from "./room-client";
import type {
  AcceptedCommandResponse,
  PreparedRoomCommand,
  RejectedCommandResponse,
  RoomCommandReceiptResponse,
  RoomCommandResponse,
} from "./types";

const RECEIPT_DELAYS_MS = [0, 250, 750, 1_500] as const;
// The 40-second window spans the backend's 30-second processing lease for stale reclaim.
const RECEIPT_ROUNDS = 16;
const RECOVERY_WINDOW_MS = 40_000;
const RECOVERY_REQUEST_TIMEOUT_MS = 5_000;
const STORAGE_VERSION = 1 as const;
const STORAGE_PREFIX = "mp3:pending-room-command:v1";
const STORAGE_LOCK_PREFIX = "mp3:pending-room-command-lock:v1";
const STORAGE_LOCK_ATTEMPTS = 8;
const STORAGE_LOCK_DELAY_MS = 20;
const STORAGE_LOCK_LEASE_MS = 1_000;
const REPLAY_LEASE_MS = 15_000;

type ReplayLease = {
  owner_id: string;
  expires_at_ms: number;
};

export type PersistedRoomCommand = {
  version: typeof STORAGE_VERSION;
  session_id: string;
  member_id: string;
  replay_lease: ReplayLease | null;
  serialized_envelope: string;
};

export type PersistedRoomCommandClaim = {
  record: PersistedRoomCommand;
  claimed: boolean;
};

export type RoomCommandTerminal =
  | { status: "accepted"; response: AcceptedCommandResponse }
  | {
      status: "rejected";
      response: RejectedCommandResponse | null;
      error: MultiplayerClientError;
    };

type ProcessingListener = (commandId: string) => void;
type BrowserLockManager = {
  request<T>(
    name: string,
    options: { signal: AbortSignal },
    callback: () => Promise<T> | T,
  ): Promise<T>;
};
type PersistedStorageLock = {
  token: string;
  expires_at: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isReplayLease(value: unknown): value is ReplayLease {
  return isRecord(value)
    && typeof value.owner_id === "string"
    && typeof value.expires_at_ms === "number"
    && Number.isFinite(value.expires_at_ms);
}

function isPreparedRoomCommand(value: unknown): value is PreparedRoomCommand {
  if (!isRecord(value) || !isRecord(value.payload)) return false;
  return typeof value.command_id === "string"
    && typeof value.expected_revision === "number"
    && Number.isInteger(value.expected_revision)
    && value.expected_revision >= 0
    && typeof value.type === "string";
}

function isRoomCommandResponse(value: unknown): value is RoomCommandResponse {
  if (!isRecord(value)) return false;
  if (
    typeof value.command_id !== "string"
    || typeof value.revision !== "number"
    || typeof value.event_sequence !== "number"
    || typeof value.replayed !== "boolean"
  ) return false;
  if (value.status === "accepted") {
    return isRecord(value.result)
      && Array.isArray(value.result.event_ids)
      && value.result.event_ids.every((item) => typeof item === "string")
      && value.error === null;
  }
  if (value.status !== "rejected" || value.result !== null || !isRecord(value.error)) {
    return false;
  }
  return typeof value.error.code === "string"
    && typeof value.error.message === "string"
    && isRecord(value.error.details);
}

function envelopeFrom(record: PersistedRoomCommand): PreparedRoomCommand {
  let parsed: unknown;
  try {
    parsed = JSON.parse(record.serialized_envelope);
  } catch {
    throw new MultiplayerClientError(
      409,
      "COMMAND_STORAGE_INVALID",
      "保存的待恢复命令格式无效。",
    );
  }
  if (!isPreparedRoomCommand(parsed)) {
    throw new MultiplayerClientError(
      409,
      "COMMAND_STORAGE_INVALID",
      "保存的待恢复命令格式无效。",
    );
  }
  return parsed;
}

function terminalFromResponse(
  response: RoomCommandResponse,
  commandId: string,
): RoomCommandTerminal {
  if (response.command_id !== commandId) {
    throw new MultiplayerClientError(
      409,
      "COMMAND_RECEIPT_INVALID",
      "命令回执与待恢复命令不匹配。",
      { command_id: commandId },
    );
  }
  if (response.status === "accepted") return { status: "accepted", response };
  return {
    status: "rejected",
    response,
    error: new MultiplayerClientError(
      422,
      response.error.code,
      response.error.message,
      response.error.details,
    ),
  };
}

function terminalFromReceipt(
  receipt: RoomCommandReceiptResponse,
  commandId: string,
): RoomCommandTerminal | null {
  if (receipt.command_id !== commandId) {
    throw new MultiplayerClientError(
      409,
      "COMMAND_RECEIPT_INVALID",
      "命令回执与待恢复命令不匹配。",
      { command_id: commandId },
    );
  }
  if (receipt.status === "processing") return null;
  if (receipt.status === "succeeded") {
    if (!isRoomCommandResponse(receipt.result) || receipt.result.status !== "accepted") {
      throw new MultiplayerClientError(
        409,
        "COMMAND_RECEIPT_INVALID",
        "命令成功回执缺少可验证结果。",
        { command_id: commandId },
      );
    }
    return terminalFromResponse(receipt.result, commandId);
  }
  if (receipt.status === "rejected") {
    const candidate = receipt.error_details.command_result;
    if (isRoomCommandResponse(candidate) && candidate.status === "rejected") {
      return terminalFromResponse(candidate, commandId);
    }
    return {
      status: "rejected",
      response: null,
      error: new MultiplayerClientError(
        422,
        receipt.error_code ?? "COMMAND_REJECTED",
        "命令已被服务器拒绝。",
        { command_id: commandId },
      ),
    };
  }
  return {
    status: "rejected",
    response: null,
    error: new MultiplayerClientError(
      409,
      receipt.error_code ?? "COMMAND_FAILED",
      "命令恢复失败。",
      { command_id: commandId },
    ),
  };
}

function isResolutionAmbiguous(error: unknown) {
  if (!(error instanceof MultiplayerClientError)) return true;
  if (error.status >= 500 || [408, 425, 429].includes(error.status)) return true;
  if (["COMMAND_IN_PROGRESS", "COMMAND_ATTEMPT_FENCED", "COMMAND_RECEIPT_INVALID"].includes(error.code)) {
    return true;
  }
  if (error.status === 409) return error.code !== "COMMAND_ID_REUSED";
  return ![400, 401, 403, 404, 405, 413, 415, 422].includes(error.status);
}

function terminalFromDefiniteSubmissionError(error: unknown): RoomCommandTerminal | null {
  if (!(error instanceof MultiplayerClientError) || isResolutionAmbiguous(error)) return null;
  return { status: "rejected", response: null, error };
}

function abortReason(signal: AbortSignal) {
  return signal.reason instanceof Error
    ? signal.reason
    : new DOMException("The operation was aborted.", "AbortError");
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw abortReason(signal);
}

function recoveryRequestTimeout() {
  return new MultiplayerClientError(
    408,
    "COMMAND_RECOVERY_REQUEST_TIMEOUT",
    "命令恢复请求超时。",
  );
}

export async function withCommandRecoveryRequestDeadline<T>(
  request: (signal: AbortSignal) => Promise<T>,
  signal?: AbortSignal,
  timeoutMs = RECOVERY_REQUEST_TIMEOUT_MS,
): Promise<T> {
  throwIfAborted(signal);
  if (timeoutMs <= 0) throw recoveryRequestTimeout();

  const controller = new AbortController();
  let timeoutId: number | null = null;
  let handleAbort: (() => void) | null = null;
  const guards: Promise<T>[] = [request(controller.signal)];
  guards.push(new Promise<T>((_resolve, reject) => {
    timeoutId = window.setTimeout(() => {
      controller.abort();
      reject(recoveryRequestTimeout());
    }, timeoutMs);
  }));
  if (signal) {
    guards.push(new Promise<T>((_resolve, reject) => {
      handleAbort = () => {
        controller.abort();
        reject(abortReason(signal));
      };
      signal.addEventListener("abort", handleAbort, { once: true });
    }));
  }

  try {
    return await Promise.race(guards);
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId);
    if (signal && handleAbort) signal.removeEventListener("abort", handleAbort);
  }
}

function wait(milliseconds: number, signal?: AbortSignal) {
  throwIfAborted(signal);
  return new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      if (signal) signal.removeEventListener("abort", handleAbort);
      resolve();
    }, milliseconds);
    const handleAbort = () => {
      window.clearTimeout(timeoutId);
      reject(signal ? abortReason(signal) : new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}

export function pendingRoomCommandStorageKey(sessionId: string, memberId: string) {
  return `${STORAGE_PREFIX}:${sessionId}:${memberId}`;
}

export function persistedRoomCommandId(record: PersistedRoomCommand) {
  return envelopeFrom(record).command_id;
}

export function createPersistedRoomCommand(
  sessionId: string,
  memberId: string,
  command: PreparedRoomCommand,
): PersistedRoomCommand {
  return {
    version: STORAGE_VERSION,
    session_id: sessionId,
    member_id: memberId,
    replay_lease: null,
    serialized_envelope: JSON.stringify(command),
  };
}

function writePersistedRoomCommand(record: PersistedRoomCommand) {
  if (typeof window === "undefined") {
    throw new MultiplayerClientError(
      409,
      "COMMAND_STORAGE_UNAVAILABLE",
      "当前环境无法保存待恢复命令。",
    );
  }
  try {
    window.localStorage.setItem(
      pendingRoomCommandStorageKey(record.session_id, record.member_id),
      JSON.stringify(record),
    );
  } catch {
    throw new MultiplayerClientError(
      409,
      "COMMAND_STORAGE_UNAVAILABLE",
      "无法保存待恢复命令，请检查浏览器存储设置。",
    );
  }
}

export function readPersistedRoomCommand(
  sessionId: string,
  memberId: string,
): PersistedRoomCommand | null {
  if (typeof window === "undefined") return null;
  const key = pendingRoomCommandStorageKey(sessionId, memberId);
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      isRecord(parsed)
      && parsed.version === STORAGE_VERSION
      && parsed.session_id === sessionId
      && parsed.member_id === memberId
      && (parsed.replay_lease === undefined || parsed.replay_lease === null || isReplayLease(parsed.replay_lease))
      && (parsed.replay_attempted === undefined || typeof parsed.replay_attempted === "boolean")
      && typeof parsed.serialized_envelope === "string"
    ) {
      const record: PersistedRoomCommand = {
        version: STORAGE_VERSION,
        session_id: sessionId,
        member_id: memberId,
        // Legacy permanent markers are intentionally reclaimed. Server-side command IDs keep replay idempotent.
        replay_lease: isReplayLease(parsed.replay_lease) ? parsed.replay_lease : null,
        serialized_envelope: parsed.serialized_envelope,
      };
      envelopeFrom(record);
      return record;
    }
  } catch {
    // Malformed browser state is left untouched so a locked writer can replace it safely.
  }
  return null;
}

function persistedRoomCommandLockKey(record: PersistedRoomCommand) {
  return `${STORAGE_LOCK_PREFIX}:${record.session_id}:${record.member_id}`;
}

function browserLockManager(): BrowserLockManager | null {
  if (typeof navigator === "undefined") return null;
  return (navigator as Navigator & { locks?: BrowserLockManager }).locks ?? null;
}

function readPersistedStorageLock(key: string): PersistedStorageLock | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      isRecord(parsed)
      && typeof parsed.token === "string"
      && typeof parsed.expires_at === "number"
    ) {
      return { token: parsed.token, expires_at: parsed.expires_at };
    }
  } catch {
    return null;
  }
  return null;
}

function storageLockBusyError() {
  return new MultiplayerClientError(
    409,
    "COMMAND_STORAGE_BUSY",
    "另一标签页正在恢复上一条命令。",
  );
}

async function withPersistedRoomCommandStorageLock<T>(
  record: PersistedRoomCommand,
  operation: () => Promise<T> | T,
  signal?: AbortSignal,
): Promise<T> {
  throwIfAborted(signal);
  const lockKey = persistedRoomCommandLockKey(record);
  const lockManager = browserLockManager();
  if (lockManager) {
    const controller = new AbortController();
    let acquired = false;
    let timedOut = false;
    const handleAbort = () => controller.abort();
    signal?.addEventListener("abort", handleAbort, { once: true });
    const timeoutId = window.setTimeout(() => {
      if (acquired) return;
      timedOut = true;
      controller.abort();
    }, STORAGE_LOCK_LEASE_MS);
    try {
      return await lockManager.request(
        lockKey,
        { signal: controller.signal },
        () => {
          acquired = true;
          window.clearTimeout(timeoutId);
          return operation();
        },
      );
    } catch (error) {
      throwIfAborted(signal);
      if (timedOut) throw storageLockBusyError();
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
      signal?.removeEventListener("abort", handleAbort);
    }
  }

  const token = createUuid();
  for (let attempt = 0; attempt < STORAGE_LOCK_ATTEMPTS; attempt += 1) {
    throwIfAborted(signal);
    const now = Date.now();
    const current = readPersistedStorageLock(lockKey);
    if (!current || current.expires_at <= now) {
      try {
        window.localStorage.setItem(lockKey, JSON.stringify({
          token,
          expires_at: now + STORAGE_LOCK_LEASE_MS,
        } satisfies PersistedStorageLock));
      } catch {
        throw new MultiplayerClientError(
          409,
          "COMMAND_STORAGE_UNAVAILABLE",
          "无法锁定待恢复命令，请检查浏览器存储设置。",
        );
      }
      await wait(STORAGE_LOCK_DELAY_MS, signal);
      if (readPersistedStorageLock(lockKey)?.token === token) {
        try {
          return await operation();
        } finally {
          try {
            if (readPersistedStorageLock(lockKey)?.token === token) {
              window.localStorage.removeItem(lockKey);
            }
          } catch {
            // The short lease lets another tab recover if lock cleanup is interrupted.
          }
        }
      }
    }
    await wait(STORAGE_LOCK_DELAY_MS * (attempt + 1), signal);
  }

  throw storageLockBusyError();
}

function claimPersistedRoomCommandSlot(
  record: PersistedRoomCommand,
): PersistedRoomCommandClaim {
  const existing = readPersistedRoomCommand(record.session_id, record.member_id);
  if (existing) return { record: existing, claimed: false };

  writePersistedRoomCommand(record);
  const stored = readPersistedRoomCommand(record.session_id, record.member_id);
  if (!stored) {
    throw new MultiplayerClientError(
      409,
      "COMMAND_STORAGE_UNAVAILABLE",
      "待恢复命令未能持久保存。",
    );
  }
  if (stored.serialized_envelope !== record.serialized_envelope) {
    return { record: stored, claimed: false };
  }
  return { record: stored, claimed: true };
}

export function claimPersistedRoomCommand(
  record: PersistedRoomCommand,
  signal?: AbortSignal,
): Promise<PersistedRoomCommandClaim> {
  return withPersistedRoomCommandStorageLock(
    record,
    () => claimPersistedRoomCommandSlot(record),
    signal,
  );
}

function claimPersistedRoomCommandReplay(
  record: PersistedRoomCommand,
  signal?: AbortSignal,
): Promise<boolean> {
  return withPersistedRoomCommandStorageLock(record, () => {
    const current = readPersistedRoomCommand(record.session_id, record.member_id);
    if (!current || current.serialized_envelope !== record.serialized_envelope) return false;
    if (current.replay_lease && current.replay_lease.expires_at_ms > Date.now()) return false;
    writePersistedRoomCommand({
      ...current,
      replay_lease: {
        owner_id: createUuid(),
        expires_at_ms: Date.now() + REPLAY_LEASE_MS,
      },
    });
    return true;
  }, signal);
}

export function clearPersistedRoomCommand(
  record: PersistedRoomCommand,
  signal?: AbortSignal,
): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  return withPersistedRoomCommandStorageLock(record, () => {
    const current = readPersistedRoomCommand(record.session_id, record.member_id);
    if (!current) return true;
    if (current.serialized_envelope !== record.serialized_envelope) return false;
    try {
      window.localStorage.removeItem(
        pendingRoomCommandStorageKey(record.session_id, record.member_id),
      );
      return true;
    } catch {
      return false;
    }
  }, signal).catch(() => false);
}

async function resolvePersistedRoomCommand(
  client: MultiplayerRoomClient,
  record: PersistedRoomCommand,
  allowPostReplay: boolean,
  onProcessing?: ProcessingListener,
  signal?: AbortSignal,
): Promise<RoomCommandTerminal> {
  const envelope = envelopeFrom(record);
  const deadlineAt = Date.now() + RECOVERY_WINDOW_MS;
  onProcessing?.(envelope.command_id);
  const requestTimeout = () => Math.min(
    RECOVERY_REQUEST_TIMEOUT_MS,
    deadlineAt - Date.now(),
  );
  const replayIfClaimed = async (
    knownProcessingReceipt: boolean,
  ): Promise<RoomCommandTerminal | null> => {
    throwIfAborted(signal);
    if (
      requestTimeout() <= 0
      || !allowPostReplay
      || !await claimPersistedRoomCommandReplay(record, signal)
    ) return null;
    try {
      const response = await withCommandRecoveryRequestDeadline(
        (requestSignal) => client.submitSerializedCommand(
          record.session_id,
          record.serialized_envelope,
          requestSignal,
        ),
        signal,
        requestTimeout(),
      );
      return terminalFromResponse(response, envelope.command_id);
    } catch (submitError) {
      throwIfAborted(signal);
      if (!knownProcessingReceipt) {
        const definiteTerminal = terminalFromDefiniteSubmissionError(submitError);
        if (definiteTerminal) return definiteTerminal;
      }
      onProcessing?.(envelope.command_id);
      return null;
    }
  };

  recovery:
  for (let round = 0; round < RECEIPT_ROUNDS; round += 1) {
    for (const delay of RECEIPT_DELAYS_MS) {
      throwIfAborted(signal);
      const remainingBeforeDelay = deadlineAt - Date.now();
      if (remainingBeforeDelay <= 0) break recovery;
      if (delay > 0) {
        await wait(Math.min(delay, remainingBeforeDelay), signal);
        if (Date.now() >= deadlineAt) break recovery;
      }
      try {
        const receipt = await withCommandRecoveryRequestDeadline(
          (requestSignal) => client.getCommandReceipt(
            record.session_id,
            envelope.command_id,
            requestSignal,
          ),
          signal,
          requestTimeout(),
        );
        const terminal = terminalFromReceipt(receipt, envelope.command_id);
        if (terminal) return terminal;
        const replayed = await replayIfClaimed(true);
        if (replayed) return replayed;
        onProcessing?.(envelope.command_id);
      } catch (error) {
        throwIfAborted(signal);
        if (
          error instanceof MultiplayerClientError
          && error.code === "COMMAND_NOT_FOUND"
        ) {
          const replayed = await replayIfClaimed(false);
          if (replayed) return replayed;
          onProcessing?.(envelope.command_id);
          continue;
        }
        if (!isResolutionAmbiguous(error)) throw error;
        onProcessing?.(envelope.command_id);
      }
    }
  }

  throw new MultiplayerClientError(
    409,
    "COMMAND_IN_PROGRESS",
    "命令状态仍不确定，请继续恢复。",
    { command_id: envelope.command_id },
  );
}

export async function submitPersistedRoomCommand(
  client: MultiplayerRoomClient,
  record: PersistedRoomCommand,
  onProcessing?: ProcessingListener,
  signal?: AbortSignal,
): Promise<RoomCommandTerminal> {
  const envelope = envelopeFrom(record);
  onProcessing?.(envelope.command_id);
  try {
    const response = await withCommandRecoveryRequestDeadline(
      (requestSignal) => client.submitSerializedCommand(
        record.session_id,
        record.serialized_envelope,
        requestSignal,
      ),
      signal,
    );
    return terminalFromResponse(response, envelope.command_id);
  } catch (error) {
    throwIfAborted(signal);
    const definiteTerminal = terminalFromDefiniteSubmissionError(error);
    if (definiteTerminal) return definiteTerminal;
    return resolvePersistedRoomCommand(client, record, true, onProcessing, signal);
  }
}

export function resumePersistedRoomCommand(
  client: MultiplayerRoomClient,
  record: PersistedRoomCommand,
  onProcessing?: ProcessingListener,
  signal?: AbortSignal,
): Promise<RoomCommandTerminal> {
  return resolvePersistedRoomCommand(client, record, true, onProcessing, signal);
}
