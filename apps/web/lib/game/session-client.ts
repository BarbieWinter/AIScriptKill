import {
  getMockEngine,
  mockCharacters,
  mockClues,
} from "@/lib/mock-data";

import type {
  ActionResponse,
  ActionType,
  Card,
  CharacterChapter,
  CharacterChapterSummary,
  ChatMessage,
  Clue,
  CommandActionResponse,
  CommandReceiptResponse,
  DurableActionEnvelope,
  Evidence,
  Review,
  SessionCharacter,
  SessionEventPage,
  SessionPresentation,
  SessionSource,
  SessionState,
  SubmissionResult,
} from "./types";

export type { SessionSource } from "./types";

const API_BASE = "/api/v1";

export class SessionClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = "SessionClientError";
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
}

export interface GameSessionClient {
  readonly source: SessionSource;
  readonly sessionId: string;
  getSession(options?: RequestOptions): Promise<SessionState>;
  getCharacters(options?: RequestOptions): Promise<{ characters: SessionCharacter[] }>;
  getClues(options?: RequestOptions): Promise<{ clues: Clue[] }>;
  getEvidences(options?: RequestOptions): Promise<{ evidences: Evidence[] }>;
  getChatHistory(options?: RequestOptions): Promise<{
    messages: ChatMessage[];
    next_page_token?: string;
  }>;
  getCards(options?: RequestOptions): Promise<{ cards: Card[] }>;
  getPresentation(options?: RequestOptions): Promise<SessionPresentation | null>;
  submitCommand?(
    envelope: DurableActionEnvelope,
    options?: RequestOptions
  ): Promise<CommandActionResponse>;
  getCommandReceipt?(
    commandId: string,
    options?: RequestOptions
  ): Promise<CommandReceiptResponse>;
  getEvents?(
    afterSequence: number,
    limit?: number,
    options?: RequestOptions
  ): Promise<SessionEventPage>;
  examine(
    sceneId: string,
    hotspotId: string,
    options?: RequestOptions
  ): Promise<ActionResponse>;
  talk(
    characterId: string,
    message: string,
    options?: RequestOptions
  ): Promise<ActionResponse>;
  showEvidence(
    characterId: string,
    evidenceId: string,
    options?: RequestOptions
  ): Promise<ActionResponse>;
  viewEvidence(
    evidenceId: string,
    options?: RequestOptions
  ): Promise<{ evidence_id: string; status: string }>;
  listCharacterChapters(
    options?: RequestOptions
  ): Promise<{ chapters: CharacterChapterSummary[] }>;
  readCharacterChapter(
    chapterId: string,
    options?: RequestOptions
  ): Promise<CharacterChapter>;
  advance(reason: string, options?: RequestOptions): Promise<ActionResponse>;
  submitJudgment(
    optionId: string,
    options?: RequestOptions
  ): Promise<SubmissionResult>;
  getReview(options?: RequestOptions): Promise<Review>;
}

async function liveRequest<T>(
  method: string,
  path: string,
  options: RequestOptions & { body?: unknown } = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { code?: string; message?: string; details?: unknown } }
      | null;
    throw new SessionClientError(
      response.status,
      payload?.error?.code ?? "UNKNOWN_ERROR",
      payload?.error?.message ?? "请求失败",
      payload?.error?.details
    );
  }

  return response.json() as Promise<T>;
}

export class LiveSessionClient implements GameSessionClient {
  readonly source = "live" as const;

  constructor(public readonly sessionId: string) {}

  getSession(options?: RequestOptions) {
    return liveRequest<SessionState>("GET", `/sessions/${this.sessionId}`, options);
  }

  getCharacters(options?: RequestOptions) {
    return liveRequest<{ characters: SessionCharacter[] }>(
      "GET",
      `/sessions/${this.sessionId}/characters`,
      options
    );
  }

  getClues(options?: RequestOptions) {
    return liveRequest<{ clues: Clue[] }>(
      "GET",
      `/sessions/${this.sessionId}/clues`,
      options
    );
  }

  getEvidences(options?: RequestOptions) {
    return liveRequest<{ evidences: Evidence[] }>(
      "GET",
      `/sessions/${this.sessionId}/evidences`,
      options
    );
  }

  getChatHistory(options?: RequestOptions) {
    return liveRequest<{ messages: ChatMessage[]; next_page_token?: string }>(
      "GET",
      `/sessions/${this.sessionId}/chat-history`,
      options
    );
  }

  getCards(options?: RequestOptions) {
    return liveRequest<{ cards: Card[] }>(
      "GET",
      `/sessions/${this.sessionId}/cards`,
      options
    );
  }

  async getPresentation(options?: RequestOptions) {
    try {
      return await liveRequest<SessionPresentation>(
        "GET",
        `/sessions/${this.sessionId}/presentation`,
        options
      );
    } catch (error) {
      if (error instanceof SessionClientError && error.status === 404) return null;
      throw error;
    }
  }

  submitCommand(envelope: DurableActionEnvelope, options?: RequestOptions) {
    return liveRequest<CommandActionResponse>(
      "POST",
      `/sessions/${this.sessionId}/actions`,
      { ...options, body: envelope }
    );
  }

  getCommandReceipt(commandId: string, options?: RequestOptions) {
    return liveRequest<CommandReceiptResponse>(
      "GET",
      `/sessions/${this.sessionId}/commands/${encodeURIComponent(commandId)}`,
      options
    );
  }

  getEvents(
    afterSequence: number,
    limit = 100,
    options?: RequestOptions
  ) {
    const query = new URLSearchParams({
      after_sequence: String(afterSequence),
      limit: String(limit),
    });
    return liveRequest<SessionEventPage>(
      "GET",
      `/sessions/${this.sessionId}/events?${query}`,
      options
    );
  }

  private performAction(
    action: ActionType,
    params: Record<string, unknown>,
    options?: RequestOptions
  ) {
    return liveRequest<ActionResponse>(
      "POST",
      `/sessions/${this.sessionId}/actions`,
      { ...options, body: { action, ...params } }
    );
  }

  examine(sceneId: string, hotspotId: string, options?: RequestOptions) {
    return this.performAction(
      "examine_scene",
      { scene_id: sceneId, hotspot_id: hotspotId },
      options
    );
  }

  talk(characterId: string, message: string, options?: RequestOptions) {
    return this.performAction(
      "talk_to_npc",
      { character_id: characterId, message },
      options
    );
  }

  showEvidence(characterId: string, evidenceId: string, options?: RequestOptions) {
    return this.performAction(
      "show_evidence",
      { character_id: characterId, evidence_id: evidenceId },
      options
    );
  }

  viewEvidence(evidenceId: string, options?: RequestOptions) {
    return liveRequest<{ evidence_id: string; status: string }>(
      "POST",
      `/sessions/${this.sessionId}/evidences/${encodeURIComponent(evidenceId)}/viewed`,
      options
    );
  }

  listCharacterChapters(options?: RequestOptions) {
    return liveRequest<{ chapters: CharacterChapterSummary[] }>(
      "GET",
      `/sessions/${this.sessionId}/character-chapters`,
      options
    );
  }

  readCharacterChapter(chapterId: string, options?: RequestOptions) {
    return liveRequest<CharacterChapter>(
      "GET",
      `/sessions/${this.sessionId}/character-chapters/${encodeURIComponent(chapterId)}`,
      options
    );
  }

  advance(reason: string, options?: RequestOptions) {
    return this.performAction("request_advance", { reason }, options);
  }

  submitJudgment(optionId: string, options?: RequestOptions) {
    return liveRequest<SubmissionResult>(
      "POST",
      `/sessions/${this.sessionId}/final-submission`,
      { ...options, body: { option: optionId } }
    );
  }

  getReview(options?: RequestOptions) {
    return liveRequest<Review>(
      "GET",
      `/sessions/${this.sessionId}/review`,
      options
    );
  }
}

const MOCK_CARDS: Card[] = [
  {
    id: "interrogation_card",
    name: "质问卡",
    type: "skill",
    image_url: "",
    description: "严厉质问一个角色，使其紧张度大幅上升",
    max_uses: 3,
    remaining_uses: 2,
    available: true,
  },
  {
    id: "empathy_card",
    name: "共情卡",
    type: "skill",
    image_url: "",
    description: "与角色共情，提升信任度",
    max_uses: 2,
    remaining_uses: 1,
    available: true,
  },
];

function throwIfAborted(options?: RequestOptions) {
  if (options?.signal?.aborted) {
    throw new DOMException("The operation was aborted", "AbortError");
  }
}

export class MockSessionClient implements GameSessionClient {
  readonly source = "mock" as const;
  private readonly viewedEvidenceIds = new Set<string>();

  constructor(public readonly sessionId: string) {}

  async getSession(options?: RequestOptions): Promise<SessionState> {
    throwIfAborted(options);
    const engine = getMockEngine();
    const stage = engine.getStage();
    const scene = engine.getCurrentScene();
    return {
      session_id: this.sessionId,
      script_id: "snow-village",
      status: "in_progress",
      current_stage: stage.id,
      stage_name: stage.name,
      player_character_id: "zhuosiyuan",
      available_actions: stage.available_actions as ActionType[],
      available_characters: stage.available_characters,
      unlocked_clues_count: engine.getUnlockedClues().length,
      total_clues_in_round: mockClues.filter((clue) => clue.stage === stage.id).length,
      discovered_evidences: engine.getDiscoveredEvidences().map((item) => item.id),
      viewed_evidences: [...this.viewedEvidenceIds],
      current_scene: scene.id,
      pending_media: [],
      revision: 0,
      event_head_sequence: 0,
    };
  }

  async getCharacters(options?: RequestOptions) {
    throwIfAborted(options);
    const available = new Set(getMockEngine().getStage().available_characters);
    return {
      characters: mockCharacters.map((character) => ({
        id: character.id,
        name: character.name,
        portrait_url: character.portrait_url ?? "",
        current_mood: "normal",
        mood_description: "表情平静",
        dialogue_available: available.has(character.id) && !character.playable,
      })),
    };
  }

  async getClues(options?: RequestOptions) {
    throwIfAborted(options);
    return { clues: getMockEngine().getUnlockedClues() as Clue[] };
  }

  async getEvidences(options?: RequestOptions) {
    throwIfAborted(options);
    const engine = getMockEngine();
    return {
      evidences: engine.getDiscoveredEvidences().map((evidence) => ({
        ...evidence,
        status: this.viewedEvidenceIds.has(evidence.id) ? "viewed" : evidence.status,
        shown_to_characters: engine.evidenceShown[evidence.id] ?? [],
      })) as Evidence[],
    };
  }

  async getChatHistory(options?: RequestOptions) {
    throwIfAborted(options);
    return { messages: [...getMockEngine().chatHistory] as ChatMessage[] };
  }

  async getCards(options?: RequestOptions) {
    throwIfAborted(options);
    return { cards: MOCK_CARDS.map((card) => ({ ...card })) };
  }

  async getPresentation(options?: RequestOptions): Promise<SessionPresentation> {
    throwIfAborted(options);
    const engine = getMockEngine();
    const stage = engine.getStage();
    const scene = engine.getCurrentScene();
    return {
      stage: {
        id: stage.id,
        name: stage.name,
        available_actions: stage.available_actions as ActionType[],
        available_characters: stage.available_characters,
      },
      scene: scene
        ? {
            id: scene.id,
            name: scene.name,
            description: scene.description,
            background_url: "",
            ambient_color: scene.bg_color,
            hotspots: scene.hotspots,
          }
        : null,
      judgement: null,
    };
  }

  async examine(sceneId: string, hotspotId: string, options?: RequestOptions) {
    throwIfAborted(options);
    return getMockEngine().examineScene(sceneId, hotspotId) as ActionResponse;
  }

  async talk(
    characterId: string,
    message: string,
    options?: RequestOptions
  ): Promise<ActionResponse> {
    throwIfAborted(options);
    const response = getMockEngine().sendMessage(characterId, message);
    if (!response) return { type: "ack", action: "talk_to_npc", status: "ok" };
    return {
      type: "npc_response",
      character_id: characterId,
      ...response,
    } as ActionResponse;
  }

  async showEvidence(
    characterId: string,
    evidenceId: string,
    options?: RequestOptions
  ) {
    throwIfAborted(options);
    return getMockEngine().showEvidence(characterId, evidenceId) as ActionResponse;
  }

  async viewEvidence(evidenceId: string, options?: RequestOptions) {
    throwIfAborted(options);
    this.viewedEvidenceIds.add(evidenceId);
    return { evidence_id: evidenceId, status: "viewed" };
  }

  async listCharacterChapters(options?: RequestOptions) {
    throwIfAborted(options);
    return { chapters: [] };
  }

  async readCharacterChapter(chapterId: string, options?: RequestOptions) {
    throwIfAborted(options);
    return {
      id: chapterId,
      character_id: "zhuosiyuan",
      order: 1,
      title: "人物章节",
      status: "viewed",
      content: "Mock 模式的人物章节由旧交互流程提供。",
    };
  }

  async advance(reason: string, options?: RequestOptions) {
    throwIfAborted(options);
    return getMockEngine().requestAdvance(reason) as ActionResponse;
  }

  async submitJudgment(
    optionId: string,
    options?: RequestOptions
  ): Promise<SubmissionResult> {
    throwIfAborted(options);
    const correct = optionId === "C";
    return {
      type: "submission_result",
      correct,
      score: correct ? 100 : 0,
      detail: {
        selected_option: optionId,
        correct_option: "C",
        evidence_boundary: correct
          ? "后门半开是已证实事实，但开门者和目的仍不可确认。"
          : "这项判断超出了当前材料能够证实的范围。",
        npc_disclosure: correct
          ? "后门当时确实开着。我后来发现门闩没扣严，就重新扣好了；我没看见是谁开的。"
          : null,
      },
      ending_id: correct
        ? "back_door_judgement_supported"
        : "back_door_judgement_unsupported",
      triggered_events: [],
    };
  }

  async getReview(options?: RequestOptions) {
    throwIfAborted(options);
    return getMockEngine().getReview() as Review;
  }
}

export function createSessionClient(
  source: SessionSource,
  sessionId: string
): GameSessionClient {
  return source === "live"
    ? new LiveSessionClient(sessionId)
    : new MockSessionClient(sessionId);
}
