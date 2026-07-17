"use client";

import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
} from "react";
import { useStore } from "zustand";

import {
  createSessionClient,
  type GameSessionClient,
} from "@/lib/game/session-client";
import type {
  ActionResponse,
  AvailableCharacter,
  Evidence,
  GameSessionSnapshot,
  Review,
  SessionCharacter,
  SessionPresentation,
  SessionSource,
  SubmissionResult,
} from "@/lib/game/types";
import {
  createGameStore,
  type GameStore,
  type GameStoreApi,
  type RuntimeStatePatch,
} from "@/stores/gameStore";

export interface GameSessionRuntime {
  readonly source: SessionSource;
  readonly sessionId: string;
  readonly sessionKey: string;
  refreshAll(): Promise<GameSessionSnapshot | null>;
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

class SessionRuntime implements GameSessionRuntime {
  readonly sessionKey: string;
  private refreshGeneration = 0;
  private refreshController: AbortController | null = null;

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
    controller: AbortController
  ) {
    if (isAbortError(error) || !this.canApply(generation, controller)) return false;
    this.store.getState().setHydration("error", errorMessage(error));
    return true;
  }

  async refreshAll(): Promise<GameSessionSnapshot | null> {
    const { controller, generation } = this.beginRefresh(true);
    const options = { signal: controller.signal };

    try {
      // The six authoritative resources form one snapshot. Presentation is a
      // seventh, independently deployable projection (live 404 becomes null).
      const [session, characters, clues, evidences, chat, cards, presentation] =
        await Promise.all([
          this.client.getSession(options),
          this.client.getCharacters(options),
          this.client.getClues(options),
          this.client.getEvidences(options),
          this.client.getChatHistory(options),
          this.client.getCards(options),
          this.client.getPresentation(options),
        ]);

      if (!this.canApply(generation, controller)) return null;

      const snapshot: GameSessionSnapshot = {
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
      };
      this.store.getState().applySnapshot(snapshot);
      return snapshot;
    } catch (error) {
      if (this.handleRefreshError(error, generation, controller)) throw error;
      return null;
    }
  }

  private async refreshAfterDiscovery() {
    const { controller, generation } = this.beginRefresh(false);
    const options = { signal: controller.signal };
    try {
      const [session, characters, clues, evidences, chat, presentation] =
        await Promise.all([
          this.client.getSession(options),
          this.client.getCharacters(options),
          this.client.getClues(options),
          this.client.getEvidences(options),
          this.client.getChatHistory(options),
          this.client.getPresentation(options),
        ]);
      if (!this.canApply(generation, controller)) return;
      this.store.getState().applyRuntimePatch({
        status: session.status,
        currentStage: session.current_stage,
        stageName: session.stage_name,
        currentScene: session.current_scene,
        availableActions: session.available_actions,
        availableCharacters: normalizeAvailableCharacters(
          session.available_characters,
          characters.characters
        ),
        playerCharacterName:
          characters.characters.find(
            (character) => character.id === session.player_character_id
          )?.name ?? session.player_character_id,
        availableScenes: availableScenes(presentation),
        totalCluesInRound: session.total_clues_in_round,
        unlockedClues: clues.clues,
        discoveredEvidences: normalizeEvidences(
          evidences.evidences,
          session.viewed_evidences
        ),
        chatMessages: chat.messages,
        presentation,
      });
    } catch (error) {
      if (this.handleRefreshError(error, generation, controller)) throw error;
    }
  }

  private async refreshAfterEvidence(includeChat: boolean) {
    const { controller, generation } = this.beginRefresh(false);
    const options = { signal: controller.signal };
    try {
      const [session, evidences, chat] = await Promise.all([
        this.client.getSession(options),
        this.client.getEvidences(options),
        includeChat ? this.client.getChatHistory(options) : Promise.resolve(null),
      ]);
      if (!this.canApply(generation, controller)) return;
      const patch: RuntimeStatePatch = {
        status: session.status,
        currentStage: session.current_stage,
        stageName: session.stage_name,
        currentScene: session.current_scene,
        availableActions: session.available_actions,
        totalCluesInRound: session.total_clues_in_round,
        discoveredEvidences: normalizeEvidences(
          evidences.evidences,
          session.viewed_evidences
        ),
      };
      if (chat) patch.chatMessages = chat.messages;
      this.store.getState().applyRuntimePatch(patch);
    } catch (error) {
      if (this.handleRefreshError(error, generation, controller)) throw error;
    }
  }

  async investigate(sceneId: string, hotspotId: string) {
    const result = await this.client.examine(sceneId, hotspotId);
    await this.refreshAfterDiscovery();
    return result;
  }

  examine(sceneId: string, hotspotId: string) {
    return this.investigate(sceneId, hotspotId);
  }

  async talk(characterId: string, message: string) {
    const result = await this.client.talk(characterId, message);
    await this.refreshAfterDiscovery();
    return result;
  }

  async showEvidence(characterId: string, evidenceId: string) {
    const result = await this.client.showEvidence(characterId, evidenceId);
    await this.refreshAfterEvidence(true);
    return result;
  }

  async viewEvidence(evidenceId: string) {
    const result = await this.client.viewEvidence(evidenceId);
    await this.refreshAfterEvidence(false);
    return result;
  }

  listCharacterChapters() {
    return this.client.listCharacterChapters();
  }

  readCharacterChapter(chapterId: string) {
    return this.client.readCharacterChapter(chapterId);
  }

  async advance(reason: string) {
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

interface SessionContexts {
  store: GameStoreApi;
  client: GameSessionClient;
  runtime: GameSessionRuntime;
}

const GameSessionContext = createContext<SessionContexts | null>(null);

export interface GameSessionProviderProps {
  source: SessionSource;
  sessionId: string;
  children: ReactNode;
  client?: GameSessionClient;
  autoRefresh?: boolean;
}

export function GameSessionProvider({
  source,
  sessionId,
  children,
  client: providedClient,
  autoRefresh = true,
}: GameSessionProviderProps) {
  const value = useMemo<SessionContexts>(() => {
    const client = providedClient ?? createSessionClient(source, sessionId);
    const store = createGameStore(source, sessionId);
    return {
      client,
      store,
      runtime: new SessionRuntime(source, sessionId, client, store),
    };
  }, [providedClient, sessionId, source]);

  useEffect(() => {
    if (autoRefresh) void value.runtime.refreshAll().catch(() => undefined);
    return () => value.runtime.cancelRefresh();
  }, [autoRefresh, value]);

  return (
    <GameSessionContext.Provider value={value}>
      {children}
    </GameSessionContext.Provider>
  );
}

export function GameSessionBoundary(props: GameSessionProviderProps) {
  return <GameSessionProvider {...props} />;
}

function useSessionContexts() {
  const contexts = useContext(GameSessionContext);
  if (!contexts) {
    throw new Error("Game session hooks must be used inside GameSessionBoundary");
  }
  return contexts;
}

export function useGameSessionRuntime() {
  return useSessionContexts().runtime;
}

export function useSessionClient() {
  return useSessionContexts().client;
}

export function useGameSessionStore<T>(selector: (state: GameStore) => T): T {
  return useStore(useSessionContexts().store, selector);
}
