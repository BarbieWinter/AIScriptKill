export type SessionSource = "live" | "mock";

export type ActionType =
  | "talk_to_npc"
  | "examine_scene"
  | "show_evidence"
  | "use_card"
  | "open_clue_board"
  | "request_advance";

export interface PendingMedia {
  id: string;
  type: string;
  status: string;
}

export interface SessionState {
  session_id: string;
  script_id: string;
  status: string;
  current_stage: string;
  stage_name: string;
  player_character_id: string;
  available_actions: ActionType[];
  available_characters: string[];
  unlocked_clues_count: number;
  total_clues_in_round: number;
  discovered_evidences: string[];
  viewed_evidences: string[];
  current_scene: string;
  pending_media: PendingMedia[];
  revision: number;
  event_head_sequence: number;
}

export interface SessionCharacter {
  id: string;
  name: string;
  portrait_url: string;
  current_mood: string;
  mood_description: string;
  dialogue_available: boolean;
}

export interface AvailableCharacter {
  id: string;
  name: string;
  mood: string;
}

export interface Clue {
  id: string;
  name: string;
  image_url: string;
  description: string;
  is_key: boolean;
  importance: number;
  discovered_at?: string;
  status: string;
}

export interface Evidence {
  id: string;
  name: string;
  image_url: string;
  description?: string;
  description_surface?: string;
  status: string;
  can_show_to_npc: boolean;
  shown_to_characters: string[];
}

export interface ChatMessage {
  id: string;
  role: string;
  character_id: string | null;
  text: string;
  timestamp: string;
  emotion?: string | null;
}

export interface Card {
  id: string;
  name: string;
  type: string;
  image_url: string;
  description: string;
  max_uses: number;
  remaining_uses: number;
  available: boolean;
}

export interface CharacterChapterSummary {
  id: string;
  character_id: string;
  order: number;
  title: string;
  status: string;
}

export interface CharacterChapter extends CharacterChapterSummary {
  content: string;
}

export interface PresentationHotspot {
  id: string;
  label: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
}

export interface PresentationScene {
  id: string;
  name: string;
  description?: string;
  background_url?: string;
  ambient_color?: string;
  hotspots: PresentationHotspot[];
}

export interface PresentationStage {
  id: string;
  name: string;
  available_actions: ActionType[];
  available_characters: string[];
}

export interface JudgementOption {
  id: string;
  text: string;
}

export interface JudgementPresentation {
  title?: string;
  question: string;
  options: JudgementOption[];
}

export interface SessionPresentation {
  stage: PresentationStage;
  scene: PresentationScene | null;
  judgement: JudgementPresentation | null;
}

export interface GameSessionSnapshot {
  source: SessionSource;
  sessionKey: string;
  sessionId: string;
  scriptId: string;
  playerCharacterId: string;
  status: string;
  currentStage: string;
  stageName: string;
  currentScene: string;
  availableActions: ActionType[];
  availableCharacters: AvailableCharacter[];
  availableScenes: Array<{ id: string; name: string }>;
  totalCluesInRound: number;
  unlockedClues: Clue[];
  discoveredEvidences: Evidence[];
  chatMessages: ChatMessage[];
  cards: Card[];
  presentation: SessionPresentation | null;
  revision: number;
  eventCursor: number;
}

export interface MediaTrigger {
  action: string;
  asset_id: string;
}

export interface EventTrigger {
  action: string;
  asset_id?: string | null;
  text?: string | null;
}

export interface NpcResponse {
  type: "npc_response";
  character_id: string;
  text: string;
  emotion: string;
  state_changes: Record<string, string | number | boolean>;
  triggered_events: string[];
  media_triggers: MediaTrigger[];
}

export interface SceneResult {
  type: "scene_result";
  scene_id: string;
  hotspot_id: string;
  dm_narration: string;
  discovered_clues: Array<{ clue_id?: string; id?: string; name: string }>;
  discovered_evidences: Array<string | Evidence>;
  media_triggers: MediaTrigger[];
}

export interface EvidenceReaction {
  type: "evidence_reaction";
  character_id: string;
  text: string;
  emotion: string;
  state_changes: Record<string, string | number | boolean>;
  triggered_dialog?: string;
  triggered_events?: string[];
  media_triggers: MediaTrigger[];
}

export interface StageTransition {
  type: "stage_transition";
  from_stage: string;
  to_stage: string;
  stage_name?: string;
  transition_events: EventTrigger[];
  new_state: {
    current_stage: string;
    available_actions: ActionType[];
  };
}

export interface AdvanceDenied {
  type: "advance_denied";
  reason: string;
  hint: string;
  suggested_action: ActionType | string;
  suggested_target: string;
  requirements?: Array<{ label: string; met: boolean }>;
}

export interface CardResult {
  type: "card_result";
  card_id: string;
  remaining_uses: number;
  effect: string;
  character_id: string;
  text: string;
  effect_description: string;
}

export interface ActionAcknowledgement {
  type: "ack";
  action: string;
  status: string;
}

export type ActionResponse =
  | NpcResponse
  | SceneResult
  | EvidenceReaction
  | CardResult
  | StageTransition
  | AdvanceDenied
  | ActionAcknowledgement;

export type DurableActionPayload = {
  action: ActionType;
  [key: string]: unknown;
};

export interface DurableActionEnvelope extends DurableActionPayload {
  command_id: string;
  expected_revision: number;
}

export interface CommandActionResponse {
  command_id: string;
  status: "succeeded" | "rejected" | "failed";
  revision: number;
  event_sequence_from: number | null;
  event_sequence_to: number | null;
  result: ActionResponse | null;
  error_code: string | null;
  error_details: Record<string, unknown>;
}

export interface CommandReceiptResponse extends Omit<CommandActionResponse, "status"> {
  status: "processing" | "succeeded" | "rejected" | "failed";
}

export interface SessionEvent {
  sequence: number;
  revision: number;
  command_id: string;
  event_type: string;
  event_version: number;
  payload: Record<string, unknown>;
  state_sha256: string | null;
}

export interface SessionEventPage {
  revision: number;
  event_head_sequence: number;
  snapshot: SessionState;
  events: SessionEvent[];
  next_after_sequence: number;
  has_more: boolean;
  reset_required: boolean;
}

export type RecoveryStatus =
  | "idle"
  | "submitting"
  | "resolving"
  | "resyncing"
  | "uncertain"
  | "conflict"
  | "error";

export interface SubmissionResult {
  type: "submission_result";
  correct: boolean;
  score: number;
  detail: Record<string, unknown>;
  ending_id: string;
  triggered_events: EventTrigger[];
}

export interface ReviewBreakdown {
  suspect_correct: boolean;
  motive_correct: boolean;
  key_evidence_hit_rate: string;
  wrong_accusations: number;
  total_clues_found: number;
  total_clues_available: number;
  clue_coverage: string;
  hints_used: number;
}

export interface Review {
  session_id: string;
  script_id: string;
  score: number;
  max_score: number;
  rating: string;
  duration_minutes: number;
  breakdown: ReviewBreakdown;
  missed_key_clues: Array<{ id: string; name: string; description: string }>;
  optimal_path: string[];
  player_path: string[];
  truth_summary: string;
}

export interface SessionResources {
  session: SessionState;
  characters: SessionCharacter[];
  clues: Clue[];
  evidences: Evidence[];
  messages: ChatMessage[];
  cards: Card[];
  presentation: SessionPresentation | null;
}
