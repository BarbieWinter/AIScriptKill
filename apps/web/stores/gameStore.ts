/** Shared game state plus session-scoped vanilla store construction. */

import { create } from "zustand";
import { createStore, type StoreApi } from "zustand/vanilla";

import type {
  ActionType,
  AvailableCharacter,
  Card,
  ChatMessage,
  Clue,
  Evidence,
  GameSessionSnapshot,
  SessionPresentation,
  SessionSource,
} from "@/lib/game/types";

export type { ActionType } from "@/lib/game/types";

export type PanelType = "clue" | "evidence" | "chapter" | "cards" | null;
export type TransitionType =
  | "scene_change"
  | "stage_change"
  | "flashback"
  | "truth_reveal"
  | null;

export interface MediaState {
  assetId: string;
  type: "bgm" | "story" | "sfx" | "voice";
  status: "playing" | "paused" | "stopped";
}

export interface RuntimeStatePatch {
  status?: string;
  currentStage?: string;
  stageName?: string;
  currentScene?: string;
  availableActions?: ActionType[];
  availableCharacters?: AvailableCharacter[];
  availableScenes?: Array<{ id: string; name: string }>;
  totalCluesInRound?: number;
  unlockedClues?: Clue[];
  discoveredEvidences?: Evidence[];
  chatMessages?: ChatMessage[];
  cards?: Card[];
  presentation?: SessionPresentation | null;
}

export type ClueInput = Pick<Clue, "id" | "name"> & Partial<Clue>;
export type EvidenceInput = Pick<Evidence, "id" | "name"> & Partial<Evidence>;

export interface GameStore {
  source: SessionSource | null;
  sessionKey: string | null;
  sessionId: string | null;
  scriptId: string | null;
  playerCharacterId: string | null;
  status: string;

  currentStage: string;
  stageName: string;
  currentScene: string;
  totalCluesInRound: number;

  availableActions: ActionType[];
  availableCharacters: AvailableCharacter[];
  availableScenes: Array<{ id: string; name: string }>;

  unlockedClues: Clue[];
  discoveredEvidences: Evidence[];
  cards: Card[];
  chatMessages: ChatMessage[];
  presentation: SessionPresentation | null;

  hydrationStatus: "idle" | "loading" | "ready" | "error";
  hydrationError: string | null;
  hydratedAt: number | null;

  isNpcTyping: boolean;
  typingCharacterId: string | null;
  currentBgm: MediaState | null;
  isMediaPlaying: boolean;
  activePanel: PanelType;
  selectedHotspot: string | null;
  isTransitioning: boolean;
  transitionType: TransitionType;

  applySnapshot: (snapshot: GameSessionSnapshot) => void;
  applyRuntimePatch: (patch: RuntimeStatePatch) => void;
  setHydration: (
    status: GameStore["hydrationStatus"],
    error?: string | null
  ) => void;
  setSession: (sessionId: string, scriptId: string, charId: string) => void;
  setStage: (stage: string) => void;
  setScene: (sceneId: string) => void;
  setActions: (actions: ActionType[]) => void;
  setTotalCluesInRound: (total: number) => void;
  setCharacters: (characters: AvailableCharacter[]) => void;
  setClues: (clues: Clue[]) => void;
  setEvidences: (evidences: Evidence[]) => void;
  updateEvidence: (evidenceId: string, patch: Partial<Evidence>) => void;
  setMessages: (messages: ChatMessage[]) => void;
  setCards: (cards: Card[]) => void;
  addMessage: (message: ChatMessage) => void;
  setNpcTyping: (charId: string | null) => void;
  openPanel: (panel: PanelType) => void;
  closePanel: () => void;
  startTransition: (type: TransitionType) => void;
  endTransition: () => void;
  addClue: (clue: ClueInput) => void;
  addEvidence: (evidence: EvidenceInput) => void;
  setBgm: (bgm: MediaState | null) => void;
  reset: () => void;
}

function initialState(source: SessionSource | null, sessionId: string | null) {
  return {
    source,
    sessionKey: source && sessionId ? `${source}:${sessionId}` : null,
    sessionId,
    scriptId: null,
    playerCharacterId: null,
    status: "",
    currentStage: "",
    stageName: "",
    currentScene: "",
    totalCluesInRound: 0,
    availableActions: [] as ActionType[],
    availableCharacters: [] as AvailableCharacter[],
    availableScenes: [] as Array<{ id: string; name: string }>,
    unlockedClues: [] as Clue[],
    discoveredEvidences: [] as Evidence[],
    cards: [] as Card[],
    chatMessages: [] as ChatMessage[],
    presentation: null as SessionPresentation | null,
    hydrationStatus: "idle" as const,
    hydrationError: null as string | null,
    hydratedAt: null as number | null,
    isNpcTyping: false,
    typingCharacterId: null as string | null,
    currentBgm: null as MediaState | null,
    isMediaPlaying: false,
    activePanel: null as PanelType,
    selectedHotspot: null as string | null,
    isTransitioning: false,
    transitionType: null as TransitionType,
  };
}

function gameStoreCreator(source: SessionSource | null, scopedSessionId: string | null) {
  return (set: StoreApi<GameStore>["setState"]): GameStore => ({
    ...initialState(source, scopedSessionId),

    applySnapshot: (snapshot) =>
      set({
        ...snapshot,
        hydrationStatus: "ready",
        hydrationError: null,
        hydratedAt: Date.now(),
      }),

    applyRuntimePatch: (patch) =>
      set({
        ...patch,
        hydrationStatus: "ready",
        hydrationError: null,
        hydratedAt: Date.now(),
      }),

    setHydration: (hydrationStatus, hydrationError = null) =>
      set({ hydrationStatus, hydrationError }),

    setSession: (sessionId, scriptId, charId) =>
      set({ sessionId, scriptId, playerCharacterId: charId }),
    setStage: (currentStage) => set({ currentStage }),
    setScene: (currentScene) => set({ currentScene }),
    setActions: (availableActions) => set({ availableActions }),
    setTotalCluesInRound: (totalCluesInRound) => set({ totalCluesInRound }),
    setCharacters: (availableCharacters) => set({ availableCharacters }),
    setClues: (unlockedClues) => set({ unlockedClues }),
    setEvidences: (discoveredEvidences) => set({ discoveredEvidences }),
    updateEvidence: (evidenceId, patch) =>
      set((state) => ({
        discoveredEvidences: state.discoveredEvidences.map((evidence) =>
          evidence.id === evidenceId ? { ...evidence, ...patch } : evidence
        ),
      })),
    setMessages: (chatMessages) => set({ chatMessages }),
    setCards: (cards) => set({ cards }),
    addMessage: (message) =>
      set((state) => ({ chatMessages: [...state.chatMessages, message] })),
    setNpcTyping: (charId) =>
      set({ isNpcTyping: charId !== null, typingCharacterId: charId }),
    openPanel: (activePanel) => set({ activePanel }),
    closePanel: () => set({ activePanel: null }),
    startTransition: (transitionType) =>
      set({ isTransitioning: true, transitionType }),
    endTransition: () =>
      set({ isTransitioning: false, transitionType: null }),
    addClue: (clue) =>
      set((state) => {
        if (state.unlockedClues.some((item) => item.id === clue.id)) return state;
        const normalized: Clue = {
          image_url: "",
          description: "",
          is_key: false,
          importance: 0,
          status: "discovered",
          ...clue,
        };
        return { unlockedClues: [...state.unlockedClues, normalized] };
      }),
    addEvidence: (evidence) =>
      set((state) => {
        if (
          state.discoveredEvidences.some((item) => item.id === evidence.id)
        ) {
          return state;
        }
        const normalized: Evidence = {
          image_url: "",
          status: "discovered",
          can_show_to_npc: false,
          shown_to_characters: [],
          ...evidence,
        };
        return {
          discoveredEvidences: [...state.discoveredEvidences, normalized],
        };
      }),
    setBgm: (currentBgm) => set({ currentBgm }),
    reset: () => set(initialState(source, scopedSessionId)),
  });
}

export type GameStoreApi = StoreApi<GameStore>;

export function createGameStore(
  source: SessionSource,
  sessionId: string
): GameStoreApi {
  return createStore<GameStore>(gameStoreCreator(source, sessionId));
}

/** Legacy singleton retained until the existing /play panels adopt the provider. */
export const useGameStore = create<GameStore>(gameStoreCreator(null, null));
