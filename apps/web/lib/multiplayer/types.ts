export type MultiplayerRoomStatus = "lobby" | "active";
export type MultiplayerRoomRole = "host" | "player";
export type GameplayPhase = "read" | "discuss" | "settle" | "reveal";

export type PackageSummary = {
  script_id: string;
  title: string;
  version: string;
};

export type CurrentMultiplayerRoom = {
  session_id: string;
  status: MultiplayerRoomStatus;
  mode: "multiplayer_v1";
};

export type CreateMultiplayerRoomRequest = {
  mode: "multiplayer_v1";
  script_id: string;
};

export type CreateMultiplayerRoomResponse = {
  session_id: string;
  mode: "multiplayer_v1";
  status: "lobby";
  revision: number;
  member_id: string;
  created_at: string;
};

export type CreateInviteResponse = {
  invite_id: string;
  token: string;
  expires_at: string;
};

export type AcceptInviteResponse = {
  session_id: string;
  status: "lobby";
  revision: number;
  member_id: string;
};

export type LobbyMember = {
  member_id: string;
  room_role: MultiplayerRoomRole;
  character_id: string | null;
  ready: boolean;
};

export type LobbyCharacter = {
  id: string;
  name: string;
  public_description: string;
  assigned_member_id: string | null;
};

export type LobbyInvite = {
  invite_id: string;
  expires_at: string;
  uses_count: number;
  max_uses: number;
  revoked: boolean;
};

export type LobbySnapshotV1 = {
  session_id: string;
  mode: "multiplayer_v1";
  status: "lobby";
  revision: number;
  package: PackageSummary;
  capacity: {
    min_players: number;
    max_players: number;
    joined: number;
  };
  self: LobbyMember;
  members: LobbyMember[];
  characters: LobbyCharacter[];
  capabilities: {
    can_invite: boolean;
    can_assign_character: boolean;
    can_ready: boolean;
    can_start: boolean;
  };
  invites: LobbyInvite[];
};

export type GameplayChapter = {
  id: string;
  title: string;
  content: string;
};

export type GameplayMaterial = {
  id: string;
  kind: "clue" | "evidence" | "media";
  title: string;
  text: string | null;
  media_type: string | null;
  url: string | null;
};

export type GameplayDiscussionMessage = {
  sequence: number;
  message_id: string;
  stage_id: string;
  member_id: string;
  character_id: string;
  text: string;
};

export type GameplaySettlement = {
  settlement_id: string;
  mode: "secret_vote" | "shared_choice" | "final_judgment";
  question: string;
  options: Array<{ id: string; text: string }>;
  submitted_member_ids: string[];
  own_option_id: string | null;
  shared_option_id: string | null;
  outcome_id: string | null;
  revealed: boolean;
  reveal: "named_ballots" | "aggregate" | "outcome_only";
  revealed_ballots: Array<{ member_id: string; option_id: string }>;
  revealed_option_counts: Array<{ option_id: string; count: number }>;
};

export type GameplayHint = {
  id: string;
  revealed_levels: string[];
  pending_level: number | null;
  confirming_member_ids: string[];
};

export type SceneFacing = "left" | "right";

export type GameplayPlayer = {
  member_id: string;
  character_id: string;
  character_name: string;
  scene_x: number | null;
  scene_y: number | null;
  scene_facing: SceneFacing | null;
  scene_moving: boolean;
  scene_online: boolean;
};

export type ScenePresenceInput = {
  x: number;
  y: number;
  facing: SceneFacing;
  moving: boolean;
};

export type GameplaySnapshotV1 = {
  snapshot_version: 1;
  session_id: string;
  mode: "multiplayer_v1";
  status: "active" | "completed";
  revision: number;
  event_head_sequence: number;
  package: PackageSummary;
  self_member_id: string;
  stage_id: string;
  stage_name: string;
  phase: GameplayPhase;
  suggested_discussion_minutes: number | null;
  players: GameplayPlayer[];
  read_member_ids: string[];
  discussion_close_member_ids: string[];
  chapters: GameplayChapter[];
  public_materials: GameplayMaterial[];
  discussion_messages: GameplayDiscussionMessage[];
  settlement: GameplaySettlement | null;
  hints: GameplayHint[];
  can_advance: boolean;
  ending_id: string | null;
};

export type RoomSnapshotV1 = LobbySnapshotV1 | GameplaySnapshotV1;

type CommandBase<TType extends string, TPayload> = {
  command_id: string;
  expected_revision: number;
  type: TType;
  payload: TPayload;
};

type StagePayload = { stage_id: string };

export type RoomCommand =
  | CommandBase<"room.assign_character", { character_id: string }>
  | CommandBase<"room.unassign_character", Record<string, never>>
  | CommandBase<"room.ready", { ready: boolean }>
  | CommandBase<"room.start", Record<string, never>>
  | CommandBase<"stage.confirm_read", StagePayload>
  | CommandBase<"stage.advance", StagePayload>
  | CommandBase<"discussion.send_message", StagePayload & { message_id: string; text: string }>
  | CommandBase<"discussion.confirm_close", StagePayload>
  | CommandBase<"discussion.revoke_close", StagePayload>
  | CommandBase<"settlement.submit", { settlement_id: string; option_id: string }>
  | CommandBase<"settlement.confirm_shared_choice", { settlement_id: string; option_id: string }>
  | CommandBase<"hint.request", { hint_id: string; level: number }>
  | CommandBase<"hint.confirm", { hint_id: string; level: number }>
  | CommandBase<"room.resync", { last_event_sequence: number | null }>;

export type RoomCommandInput = RoomCommand extends infer T
  ? T extends RoomCommand
    ? Omit<T, "command_id">
    : never
  : never;

export type PreparedRoomCommand = RoomCommand;
export type LobbyCommandInput = Extract<
  RoomCommandInput,
  { type: "room.assign_character" | "room.unassign_character" | "room.ready" | "room.start" }
>;

export type AcceptedCommandResponse = {
  command_id: string;
  status: "accepted";
  revision: number;
  event_sequence: number;
  result: { event_ids: string[] };
  error: null;
  replayed: boolean;
};

export type RejectedCommandResponse = {
  command_id: string;
  status: "rejected";
  revision: number;
  event_sequence: number;
  result: null;
  error: {
    code: string;
    message: string;
    details: Record<string, string>;
  };
  replayed: boolean;
};

export type RoomCommandResponse = AcceptedCommandResponse | RejectedCommandResponse;
export type LobbyCommandResponse = RoomCommandResponse;

export type CompletedReviewV1 = {
  review_version: 1;
  session_id: string;
  member_id: string;
  ending: { id: string; name: string; outcome_text: string };
  chapters: Array<{
    id: string;
    character_id: string;
    title: string;
    content: string;
  }>;
  truth: {
    case_summary: string | null;
    murderer: string | null;
    victim: string | null;
    motive: string | null;
    timeline: Array<{ time: string; event: string; hidden: boolean }>;
    key_evidence_chain: string[];
    alternative_endings: Array<{
      id: string;
      condition: string;
      news_broadcast: string | null;
    }>;
  };
  final_settlement: {
    stage_id: string;
    settlement_id: string;
    outcome_id: string;
    reveal: "named_ballots" | "aggregate" | "outcome_only";
    ballots?: Array<{ member_id: string; option_id: string }>;
    option_counts?: Array<{ option_id: string; count: number }>;
  };
};

export type MultiplayerApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, string>;
  };
};
