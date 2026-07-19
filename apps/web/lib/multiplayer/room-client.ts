import { getAnonymousAccessToken } from "@/lib/auth/anonymous-session";
import type {
  AcceptInviteResponse,
  CreateInviteResponse,
  CreateMultiplayerRoomResponse,
  CurrentMultiplayerRoom,
  LobbyCommandInput,
  LobbyCommandResponse,
  LobbySnapshotV1,
  MultiplayerApiErrorBody,
} from "./types";

const API_BASE = "/api/v1";

export function lobbySnapshotKey(sessionId: string) {
  return ["multiplayer", "lobby-snapshot", sessionId] as const;
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
  method?: "GET" | "POST" | "DELETE";
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

  getSnapshot(sessionId: string, signal?: AbortSignal): Promise<LobbySnapshotV1> {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/snapshot`, { signal });
  }

  async sendCommand(
    sessionId: string,
    command: LobbyCommandInput,
    signal?: AbortSignal,
  ): Promise<LobbyCommandResponse> {
    const response = await this.request<LobbyCommandResponse>(
      `/sessions/${encodeURIComponent(sessionId)}/commands`,
      {
        method: "POST",
        body: { ...command, command_id: crypto.randomUUID() },
        signal,
      },
    );

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
}

export function createMultiplayerRoomClient(
  getAccessToken: TokenProvider = getAnonymousAccessToken,
): MultiplayerRoomClient {
  return new MultiplayerRoomClient(getAccessToken);
}
