export type MultiplayerRoomStatus = "lobby" | "active";
export type MultiplayerRoomRole = "host" | "player";

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
  status: MultiplayerRoomStatus;
  revision: number;
  package: {
    script_id: string;
    title: string;
    version: string;
  };
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

export type AssignCharacterCommand = {
  command_id: string;
  expected_revision: number;
  type: "room.assign_character";
  payload: { character_id: string };
};

export type UnassignCharacterCommand = {
  command_id: string;
  expected_revision: number;
  type: "room.unassign_character";
  payload: Record<string, never>;
};

export type ReadyCommand = {
  command_id: string;
  expected_revision: number;
  type: "room.ready";
  payload: { ready: boolean };
};

export type StartRoomCommand = {
  command_id: string;
  expected_revision: number;
  type: "room.start";
  payload: Record<string, never>;
};

export type LobbyCommand =
  | AssignCharacterCommand
  | UnassignCharacterCommand
  | ReadyCommand
  | StartRoomCommand;

export type LobbyCommandInput =
  | Omit<AssignCharacterCommand, "command_id">
  | Omit<UnassignCharacterCommand, "command_id">
  | Omit<ReadyCommand, "command_id">
  | Omit<StartRoomCommand, "command_id">;

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

export type LobbyCommandResponse =
  | AcceptedCommandResponse
  | RejectedCommandResponse;

export type MultiplayerApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, string>;
  };
};
