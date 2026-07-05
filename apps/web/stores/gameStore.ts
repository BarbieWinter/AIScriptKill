/**
 * 游戏状态管理
 * Zustand Store — 管理前端游戏状态
 *
 * 状态驱动 UI：游戏状态变化自动触发 UI 响应
 */

import { create } from "zustand";

export type PanelType = "clue" | "evidence" | "note" | "cards" | null;
export type TransitionType =
  | "scene_change"
  | "stage_change"
  | "flashback"
  | "truth_reveal"
  | null;
export type ActionType =
  | "talk_to_npc"
  | "examine_scene"
  | "show_evidence"
  | "use_card"
  | "open_clue_board"
  | "request_advance";

interface MediaState {
  assetId: string;
  type: "bgm" | "story" | "sfx" | "voice";
  status: "playing" | "paused" | "stopped";
}

interface GameStore {
  // ── 会话 ──
  sessionId: string | null;
  scriptId: string | null;
  playerCharacterId: string | null;

  // ── 游戏进度 ──
  currentStage: string;
  currentScene: string;

  // ── 操作选项 ──
  availableActions: ActionType[];
  availableCharacters: { id: string; name: string; mood: string }[];
  availableScenes: { id: string; name: string }[];

  // ── 收藏数据 ──
  unlockedClues: any[];
  discoveredEvidences: any[];
  cards: any[];

  // ── 对话 ──
  chatMessages: any[];
  isNpcTyping: boolean;
  typingCharacterId: string | null;

  // ── 媒体 ──
  currentBgm: MediaState | null;
  isMediaPlaying: boolean;

  // ── UI 状态 ──
  activePanel: PanelType;
  selectedHotspot: string | null;
  isTransitioning: boolean;
  transitionType: TransitionType;

  // ── 动作 ──
  setSession: (sessionId: string, scriptId: string, charId: string) => void;
  setStage: (stage: string) => void;
  setScene: (sceneId: string) => void;
  setActions: (actions: ActionType[]) => void;
  addMessage: (msg: any) => void;
  setNpcTyping: (charId: string | null) => void;
  openPanel: (panel: PanelType) => void;
  closePanel: () => void;
  startTransition: (type: TransitionType) => void;
  endTransition: () => void;
  addClue: (clue: any) => void;
  addEvidence: (evidence: any) => void;
  setBgm: (bgm: MediaState | null) => void;
  reset: () => void;
}

const initial = {
  sessionId: null as string | null,
  scriptId: null as string | null,
  playerCharacterId: null as string | null,
  currentStage: "",
  currentScene: "",
  availableActions: [] as ActionType[],
  availableCharacters: [],
  availableScenes: [],
  unlockedClues: [],
  discoveredEvidences: [],
  cards: [],
  chatMessages: [],
  isNpcTyping: false,
  typingCharacterId: null,
  currentBgm: null as MediaState | null,
  isMediaPlaying: false,
  activePanel: null as PanelType,
  selectedHotspot: null as string | null,
  isTransitioning: false,
  transitionType: null as TransitionType,
};

export const useGameStore = create<GameStore>((set) => ({
  ...initial,

  setSession: (sessionId, scriptId, charId) =>
    set({ sessionId, scriptId, playerCharacterId: charId }),

  setStage: (stage) => set({ currentStage: stage }),

  setScene: (sceneId) => set({ currentScene: sceneId }),

  setActions: (actions) => set({ availableActions: actions }),

  addMessage: (msg) =>
    set((state) => ({
      chatMessages: [...state.chatMessages, msg],
    })),

  setNpcTyping: (charId) =>
    set({ isNpcTyping: charId !== null, typingCharacterId: charId }),

  openPanel: (panel) => set({ activePanel: panel }),

  closePanel: () => set({ activePanel: null }),

  startTransition: (type) =>
    set({ isTransitioning: true, transitionType: type }),

  endTransition: () =>
    set({ isTransitioning: false, transitionType: null }),

  addClue: (clue) =>
    set((state) => ({
      unlockedClues: state.unlockedClues.some((c) => c.id === clue.id)
        ? state.unlockedClues
        : [...state.unlockedClues, clue],
    })),

  addEvidence: (evidence) =>
    set((state) => ({
      discoveredEvidences: state.discoveredEvidences.some(
        (e) => e.id === evidence.id
      )
        ? state.discoveredEvidences
        : [...state.discoveredEvidences, evidence],
    })),

  setBgm: (bgm) => set({ currentBgm: bgm }),

  reset: () => set(initial),
}));
