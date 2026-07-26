import { createUuid } from "@/lib/uuid";
import type {
  ActionResponse,
  ActionType,
  AvailableCharacter,
  DurableActionEnvelope,
  Evidence,
  GameSessionSnapshot,
  Review,
  SessionCharacter,
  SessionPresentation,
  SessionSource,
  SessionState,
  SubmissionResult,
} from "./types";
import {
  SessionClientError,
  type GameSessionClient,
} from "./session-client";
import type {
  GameStoreApi,
  RuntimeStatePatch,
} from "@/stores/gameStore";

export interface GameSessionRuntime {
  readonly source: SessionSource;
  readonly sessionId: string;
  readonly sessionKey: string;
  refreshAll(): Promise<GameSessionSnapshot | null>;
  resync(): Promise<GameSessionSnapshot | null>;
  retryPendingCommand(): Promise<ActionResponse | null>;
  investigate(sceneId: string, hotspotId: string): Promise<ActionResponse>;
  examine(sceneId: string, hotspotId: string): Promise<ActionResponse>;
  talk(characterId: string, message: string): Promise<ActionResponse>;
  showEvidence(characterId: string, evidenceId: string): Promise<ActionResponse>;
  viewEvidence(evidenceId: string): Promise<{ evidence_id: string; status: string }>;
  listCharacterChapters(): ReturnType<GameSessionClient["listCharacterChapters"]>;
  readCharacterChapter(
    chapterId: string
  ): ReturnType<GameSessionClient["readCharacterChapter"]>;
  advance(reason: string): Promise<ActionResponse>;
  submitJudgment(optionId: string): Promise<SubmissionResult>;
  getReview(): Promise<Review>;
  cancelRefresh(): void;
}

const RECEIPT_DELAYS_MS = [0, 250, 750, 1500] as const;
const MAX_EVENT_PAGES = 10;

function normalizeAvailableCharacters(
  sessionCharacterIds: string[],
  characters: SessionCharacter[]
): AvailableCharacter[] {
  const availableIds = new Set(sessionCharacterIds);
  return characters
    .filter(
      (character) =>
        character.dialogue_available &&
        (availableIds.size === 0 || availableIds.has(character.id))
    )
    .map((character) => ({
      id: character.id,
      name: character.name,
      mood: character.current_mood,
    }));
}

function normalizeEvidences(evidences: Evidence[], viewedIds: string[]): Evidence[] {
  const viewed = new Set(viewedIds);
  return evidences.map((evidence) => ({
    ...evidence,
    status: viewed.has(evidence.id) ? "viewed" : evidence.status,
    shown_to_characters: evidence.shown_to_characters ?? [],
  }));
}

function availableScenes(presentation: SessionPresentation | null) {
  const scene = presentation?.scene;
  return scene ? [{ id: scene.id, name: scene.name }] : [];
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "无法加载游戏会话";
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function isTransportAmbiguity(error: unknown) {
  return !(error instanceof SessionClientError) || error.status >= 500;
}

function isRevisionConflict(error: unknown): error is SessionClientError {
  return (
    error instanceof SessionClientError &&
    error.code === "SESSION_REVISION_CONFLICT"
  );
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
}

function commandStorageKey(sessionKey: string) {
  return `mp3:pending-command:${sessionKey}`;
}

function isDurableEnvelope(value: unknown): value is DurableActionEnvelope {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.command_id === "string" &&
    typeof record.expected_revision === "number" &&
    Number.isInteger(record.expected_revision) &&
    record.expected_revision >= 0 &&
    typeof record.action === "string"
  );
}

export class SessionRuntime implements GameSessionRuntime {
  readonly sessionKey: string;
  private refreshGeneration = 0;
  private refreshController: AbortController | null = null;
  private activeMutation: Promise<ActionResponse> | null = null;

  constructor(
    readonly source: SessionSource,
    readonly sessionId: string,
    private readonly client: GameSessionClient,
    private readonly store: GameStoreApi
  ) {
    this.sessionKey = `${source}:${sessionId}`;
  }

  cancelRefresh() {
    this.refreshGeneration += 1;
    this.refreshController?.abort();
    this.refreshController = null;
  }

  private beginRefresh(markLoading: boolean) {
    this.refreshController?.abort();
    const controller = new AbortController();
    const generation = ++this.refreshGeneration;
    this.refreshController = controller;
    if (markLoading) this.store.getState().setHydration("loading");
    return { controller, generation };
  }

  private canApply(generation: number, controller: AbortController) {
    return (
      generation === this.refreshGeneration &&
      !controller.signal.aborted &&
      this.store.getState().sessionKey === this.sessionKey
    );
  }

  private handleRefreshError(
    error: unknown,
    generation: number,
    controller: AbortController,
    blocking: boolean
  ) {
    if (isAbortError(error) || !this.canApply(generation, controller)) return false;
    if (blocking) {
      this.store.getState().setHydration("error", errorMessage(error));
    } else {
      this.store.getState().setRecovery("error", null, errorMessage(error));
    }
    return true;
  }

  private async buildSnapshot(
    session: SessionState,
    eventCursor: number,
    controller: AbortController,
    generation: number
  ): Promise<GameSessionSnapshot | null> {
    const options = { signal: controller.signal };
    const [characters, clues, evidences, chat, cards, presentation] =
      await Promise.all([
        this.client.getCharacters(options),
        this.client.getClues(options),
        this.client.getEvidences(options),
        this.client.getChatHistory(options),
        this.client.getCards(options),
        this.client.getPresentation(options),
      ]);
    if (!this.canApply(generation, controller)) return null;
    return {
      source: this.source,
      sessionKey: this.sessionKey,
      sessionId: session.session_id,
      scriptId: session.script_id,
      playerCharacterId: session.player_character_id,
      playerCharacterName:
        characters.characters.find(
          (character) => character.id === session.player_character_id
        )?.name ?? session.player_character_id,
      status: session.status,
      currentStage: session.current_stage,
      stageName: session.stage_name,
      currentScene: session.current_scene,
      availableActions: session.available_actions,
      availableCharacters: normalizeAvailableCharacters(
        session.available_characters,
        characters.characters
      ),
      availableScenes: availableScenes(presentation),
      totalCluesInRound: session.total_clues_in_round,
      unlockedClues: clues.clues,
      discoveredEvidences: normalizeEvidences(
        evidences.evidences,
        session.viewed_evidences
      ),
      chatMessages: chat.messages,
      cards: cards.cards,
      presentation,
      revision: session.revision,
      eventCursor,
    };
  }

  async refreshAll(): Promise<GameSessionSnapshot | null> {
    const blocking = this.store.getState().hydrationStatus !== "ready";
    const { controller, generation } = this.beginRefresh(blocking);
    try {
      const session = await this.client.getSession({ signal: controller.signal });
      const snapshot = await this.buildSnapshot(
        session,
        session.event_head_sequence,
        controller,
        generation
      );
      if (snapshot) this.store.getState().applySnapshot(snapshot);
      return snapshot;
    } catch (error) {
      if (this.handleRefreshError(error, generation, controller, blocking)) throw error;
      return null;
    }
  }

  private async eventSnapshot(
    afterSequence: number,
    allowReset: boolean,
    signal?: AbortSignal
  ): Promise<{ session: SessionState; cursor: number } | null> {
    if (!this.client.getEvents) return null;
    let cursor = afterSequence;
    let lastRevision = afterSequence === 0 ? 0 : this.store.getState().revision;
    let latest: SessionState | null = null;

    try {
      for (let pageIndex = 0; pageIndex < MAX_EVENT_PAGES; pageIndex += 1) {
        const page = await this.client.getEvents(cursor, 100, { signal });
        if (page.reset_required) throw new Error("EVENT_RESET_REQUIRED");
        if (
          page.snapshot.revision !== page.revision ||
          page.snapshot.event_head_sequence !== page.event_head_sequence ||
          page.revision < lastRevision ||
          page.event_head_sequence < cursor
        ) {
          throw new Error("EVENT_SNAPSHOT_MISMATCH");
        }
        for (const event of page.events) {
          if (event.sequence <= cursor) continue;
          if (event.sequence !== cursor + 1 || event.revision < lastRevision) {
            throw new Error("EVENT_SEQUENCE_GAP");
          }
          cursor = event.sequence;
          lastRevision = event.revision;
        }
        if (page.next_after_sequence !== cursor) {
          throw new Error("EVENT_CURSOR_MISMATCH");
        }
        latest = page.snapshot;
        if (!page.has_more) {
          if (cursor !== page.event_head_sequence) {
            throw new Error("EVENT_HEAD_MISMATCH");
          }
          return { session: latest, cursor };
        }
      }
      throw new Error("EVENT_PAGE_LIMIT");
    } catch (error) {
      if (allowReset && afterSequence !== 0) {
        return this.eventSnapshot(0, false, signal);
      }
      throw error;
    }
  }

  async resync(): Promise<GameSessionSnapshot | null> {
    if (this.source === "mock" || !this.client.getEvents) return this.refreshAll();
    this.store.getState().setRecovery("resyncing");
    const { controller, generation } = this.beginRefresh(false);
    try {
      const replay = await this.eventSnapshot(
        this.store.getState().eventCursor,
        true,
        controller.signal
      );
      if (!replay) return this.refreshAll();
      const snapshot = await this.buildSnapshot(
        replay.session,
        replay.cursor,
        controller,
        generation
      );
      if (snapshot) {
        this.store.getState().applySnapshot(snapshot);
        this.store.getState().setRecovery("idle");
      }
      return snapshot;
    } catch (error) {
      if (this.handleRefreshError(error, generation, controller, false)) throw error;
      return null;
    }
  }

  private persistEnvelope(envelope: DurableActionEnvelope | null) {
    if (typeof window === "undefined") return;
    const key = commandStorageKey(this.sessionKey);
    if (envelope) sessionStorage.setItem(key, JSON.stringify(envelope));
    else sessionStorage.removeItem(key);
  }

  private storedEnvelope() {
    if (typeof window === "undefined") return null;
    const raw = sessionStorage.getItem(commandStorageKey(this.sessionKey));
    if (!raw) return null;
    try {
      const parsed: unknown = JSON.parse(raw);
      if (isDurableEnvelope(parsed)) return parsed;
    } catch {
      // Invalid client persistence is discarded rather than treated as authority.
    }
    this.persistEnvelope(null);
    return null;
  }

  private terminalResult(
    response: {
      status: "processing" | "succeeded" | "rejected" | "failed";
      result: ActionResponse | null;
      error_code: string | null;
      error_details: Record<string, unknown>;
    },
    commandId: string
  ) {
    if (response.status === "succeeded" && response.result) return response.result;
    if (response.status === "processing") return null;
    throw new SessionClientError(
      409,
      response.error_code ?? "COMMAND_FAILED",
      "命令未能完成",
      { command_id: commandId, ...response.error_details }
    );
  }

  private async resolveEnvelope(
    envelope: DurableActionEnvelope,
    allowPostRetry: boolean
  ): Promise<ActionResponse> {
    if (!this.client.getCommandReceipt || !this.client.submitCommand) {
      throw new Error("Durable command recovery is unavailable");
    }
    this.store.getState().setRecovery("resolving", envelope.command_id);

    for (const delay of RECEIPT_DELAYS_MS) {
      if (delay) await wait(delay);
      try {
        const receipt = await this.client.getCommandReceipt(envelope.command_id);
        const terminal = this.terminalResult(receipt, envelope.command_id);
        if (terminal) return terminal;
      } catch (error) {
        if (
          error instanceof SessionClientError &&
          error.code === "COMMAND_NOT_FOUND" &&
          allowPostRetry
        ) {
          allowPostRetry = false;
          let replay;
          try {
            replay = await this.client.submitCommand(envelope);
          } catch (submitError) {
            if (isTransportAmbiguity(submitError)) continue;
            throw submitError;
          }
          const terminal = this.terminalResult(replay, envelope.command_id);
          if (terminal) return terminal;
        } else if (
          !(error instanceof SessionClientError) ||
          error.code !== "COMMAND_IN_PROGRESS"
        ) {
          throw error;
        }
      }
    }

    this.store.getState().setRecovery("uncertain", envelope.command_id);
    throw new SessionClientError(
      409,
      "COMMAND_IN_PROGRESS",
      "命令状态仍不确定，请稍后手动恢复",
      { command_id: envelope.command_id }
    );
  }

  private async submitEnvelope(envelope: DurableActionEnvelope) {
    if (!this.client.submitCommand) throw new Error("Durable commands are unavailable");
    this.persistEnvelope(envelope);
    this.store.getState().setRecovery("submitting", envelope.command_id);
    try {
      const response = await this.client.submitCommand(envelope);
      const terminal = this.terminalResult(response, envelope.command_id);
      if (!terminal) return this.resolveEnvelope(envelope, false);
      return terminal;
    } catch (error) {
      if (isRevisionConflict(error)) {
        this.persistEnvelope(null);
        this.store.getState().setRecovery("conflict", null, error.message);
        await this.resync();
        throw error;
      }
      if (
        error instanceof SessionClientError &&
        !["COMMAND_IN_PROGRESS"].includes(error.code) &&
        error.status < 500
      ) {
        this.persistEnvelope(null);
        throw error;
      }
      return this.resolveEnvelope(envelope, true);
    }
  }

  private durableAction(action: ActionType, params: Record<string, unknown>) {
    if (this.activeMutation) {
      return Promise.reject(
        new SessionClientError(409, "COMMAND_IN_PROGRESS", "另一项操作仍在恢复中")
      );
    }
    const envelope: DurableActionEnvelope = {
      action,
      ...params,
      command_id: createUuid(),
      expected_revision: this.store.getState().revision,
    };
    const operation = this.submitEnvelope(envelope)
      .then(async (result) => {
        this.persistEnvelope(null);
        try {
          await this.resync();
        } catch {
          // The command is terminally successful; reconciliation remains a separate recovery state.
        }
        return result;
      })
      .finally(() => {
        this.activeMutation = null;
      });
    this.activeMutation = operation;
    return operation;
  }

  async retryPendingCommand() {
    if (this.activeMutation) return this.activeMutation;
    const envelope = this.storedEnvelope();
    if (!envelope) {
      await this.resync();
      return null;
    }
    const operation = this.resolveEnvelope(envelope, true)
      .then(async (result) => {
        this.persistEnvelope(null);
        try {
          await this.resync();
        } catch {
          // Receipt success is final even if the authoritative resource refresh is delayed.
        }
        return result;
      })
      .finally(() => {
        this.activeMutation = null;
      });
    this.activeMutation = operation;
    return operation;
  }

  async investigate(sceneId: string, hotspotId: string) {
    if (this.source === "live") {
      return this.durableAction("examine_scene", {
        scene_id: sceneId,
        hotspot_id: hotspotId,
      });
    }
    const result = await this.client.examine(sceneId, hotspotId);
    await this.refreshAll();
    return result;
  }

  examine(sceneId: string, hotspotId: string) {
    return this.investigate(sceneId, hotspotId);
  }

  async talk(characterId: string, message: string) {
    if (this.source === "live") {
      return this.durableAction("talk_to_npc", {
        character_id: characterId,
        message,
      });
    }
    const result = await this.client.talk(characterId, message);
    await this.refreshAll();
    return result;
  }

  async showEvidence(characterId: string, evidenceId: string) {
    if (this.source === "live") {
      return this.durableAction("show_evidence", {
        character_id: characterId,
        evidence_id: evidenceId,
      });
    }
    const result = await this.client.showEvidence(characterId, evidenceId);
    await this.refreshAll();
    return result;
  }

  async viewEvidence(evidenceId: string) {
    const result = await this.client.viewEvidence(evidenceId);
    await this.refreshAll();
    return result;
  }

  listCharacterChapters() {
    return this.client.listCharacterChapters();
  }

  readCharacterChapter(chapterId: string) {
    return this.client.readCharacterChapter(chapterId);
  }

  async advance(reason: string) {
    if (this.source === "live") {
      return this.durableAction("request_advance", { reason });
    }
    const result = await this.client.advance(reason);
    await this.refreshAll();
    return result;
  }

  async submitJudgment(optionId: string) {
    const result = await this.client.submitJudgment(optionId);
    await this.refreshAll();
    return result;
  }

  getReview() {
    return this.client.getReview();
  }
}

export function createSessionRuntime(
  source: SessionSource,
  sessionId: string,
  client: GameSessionClient,
  store: GameStoreApi
) {
  return new SessionRuntime(source, sessionId, client, store);
}
