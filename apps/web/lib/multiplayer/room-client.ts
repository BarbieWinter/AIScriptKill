import { createUuid } from "@/lib/uuid";
import { getAnonymousAccessToken } from "@/lib/auth/anonymous-session";
import type {
  AcceptInviteResponse,
  CompletedReviewV1,
  CreateInviteResponse,
  CreateMultiplayerRoomResponse,
  CurrentMultiplayerRoom,
  MultiplayerApiErrorBody,
  PreparedRoomCommand,
  RoomCommandInput,
  RoomCommandResponse,
  RoomSnapshotV1,
  ScenePresenceInput,
} from "./types";

const API_BASE = "/api/v1";

export function roomSnapshotKey(sessionId: string) {
  return ["multiplayer", "room-snapshot", sessionId] as const;
}

export const lobbySnapshotKey = roomSnapshotKey;

export const currentMultiplayerRoomKey = ["multiplayer", "current-room"] as const;

export function multiplayerReviewKey(sessionId: string, memberId: string) {
  return ["multiplayer", "review", sessionId, memberId] as const;
}

export class MultiplayerClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: Record<string, string> = {},
  ) {
    super(message);
    this.name = "MultiplayerClientError";
  }
}

type TokenProvider = () => Promise<string>;

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
};

async function parseError(response: Response): Promise<MultiplayerApiErrorBody> {
  try {
    return (await response.json()) as MultiplayerApiErrorBody;
  } catch {
    return {};
  }
}

export class MultiplayerRoomClient {
  constructor(private readonly getAccessToken: TokenProvider) {}

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const token = await this.getAccessToken();
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
    };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";

    const response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });

    if (!response.ok) {
      const body = await parseError(response);
      throw new MultiplayerClientError(
        response.status,
        body.error?.code ?? "UNKNOWN_ERROR",
        body.error?.message ?? "多人房间请求失败。",
        body.error?.details ?? {},
      );
    }

    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  getCurrentRoom(signal?: AbortSignal): Promise<CurrentMultiplayerRoom | null> {
    return this.request("/sessions/current", { signal });
  }

  createRoom(scriptId: string, signal?: AbortSignal): Promise<CreateMultiplayerRoomResponse> {
    return this.request("/sessions", {
      method: "POST",
      body: { mode: "multiplayer_v1", script_id: scriptId },
      signal,
    });
  }

  createInvite(
    sessionId: string,
    ttlSeconds = 900,
    signal?: AbortSignal,
  ): Promise<CreateInviteResponse> {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/invites`, {
      method: "POST",
      body: { ttl_seconds: ttlSeconds },
      signal,
    });
  }

  revokeInvite(sessionId: string, inviteId: string, signal?: AbortSignal): Promise<void> {
    return this.request(
      `/sessions/${encodeURIComponent(sessionId)}/invites/${encodeURIComponent(inviteId)}`,
      { method: "DELETE", signal },
    );
  }

  acceptInvite(token: string, signal?: AbortSignal): Promise<AcceptInviteResponse> {
    return this.request(`/session-invites/${encodeURIComponent(token)}/accept`, {
      method: "POST",
      signal,
    });
  }

  getSnapshot(sessionId: string, signal?: AbortSignal): Promise<RoomSnapshotV1> {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/snapshot`, { signal });
  }

  getReview(sessionId: string, signal?: AbortSignal): Promise<CompletedReviewV1> {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/review`, { signal });
  }

  updateScenePresence(
    sessionId: string,
    presence: ScenePresenceInput,
    signal?: AbortSignal,
  ): Promise<void> {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/scene-presence`, {
      method: "PUT",
      body: presence,
      signal,
    });
  }

  prepareCommand(command: RoomCommandInput): PreparedRoomCommand {
    return { ...command, command_id: createUuid() } as PreparedRoomCommand;
  }

  async sendPreparedCommand(
    sessionId: string,
    command: PreparedRoomCommand,
    signal?: AbortSignal,
  ): Promise<RoomCommandResponse> {
    let response: RoomCommandResponse;
    try {
      response = await this.request<RoomCommandResponse>(
        `/sessions/${encodeURIComponent(sessionId)}/commands`,
        { method: "POST", body: command, signal },
      );
    } catch (error) {
      if (signal?.aborted || error instanceof MultiplayerClientError) throw error;
      response = await this.request<RoomCommandResponse>(
        `/sessions/${encodeURIComponent(sessionId)}/commands`,
        { method: "POST", body: command, signal },
      );
    }

    if (response.status === "rejected") {
      throw new MultiplayerClientError(
        422,
        response.error.code,
        response.error.message,
        response.error.details,
      );
    }
    return response;
  }

  sendCommand(
    sessionId: string,
    command: RoomCommandInput,
    signal?: AbortSignal,
  ): Promise<RoomCommandResponse> {
    return this.sendPreparedCommand(sessionId, this.prepareCommand(command), signal);
  }
}

export function createMultiplayerRoomClient(
  getAccessToken: TokenProvider = getAnonymousAccessToken,
): MultiplayerRoomClient {
  return new MultiplayerRoomClient(getAccessToken);
}
