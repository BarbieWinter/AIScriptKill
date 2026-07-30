import { expect, test, type Browser, type BrowserContext, type Page, type Route } from "@playwright/test";

type Identity = "host" | "guest" | "outsider";
type Member = {
  member_id: string;
  room_role: "host" | "player";
  character_id: string | null;
  ready: boolean;
};
type Invite = {
  invite_id: string;
  token: string;
  expires_at: string;
  uses_count: number;
  max_uses: number;
  revoked: boolean;
};

const sessionId = "11111111-1111-4111-8111-111111111111";
const characters = [
  { id: "detective-a", name: "侦探甲", public_description: "负责核对现场时间线" },
  { id: "detective-b", name: "侦探乙", public_description: "熟悉值班室内部流程" },
];

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function apiError(route: Route, status: number, code: string, message: string) {
  return json(route, { error: { code, message, details: {} } }, status);
}

function jwtFor(identity: Identity) {
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "none", typ: "JWT" })}.${encode({ sub: identity, exp: Math.floor(Date.now() / 1000) + 3600 })}.signature`;
}

async function installAnonymousAuth(context: BrowserContext, identity: Identity) {
  const token = jwtFor(identity);
  await context.route("**/auth/v1/signup", async (route) => {
    const now = new Date().toISOString();
    await json(route, {
      access_token: token,
      token_type: "bearer",
      expires_in: 3600,
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      refresh_token: `refresh-${identity}`,
      user: {
        id: identity,
        aud: "authenticated",
        role: "authenticated",
        email: "",
        phone: "",
        app_metadata: { provider: "anonymous", providers: ["anonymous"] },
        user_metadata: {},
        identities: [],
        created_at: now,
        updated_at: now,
        is_anonymous: true,
      },
    });
  });
  return token;
}

function createMockRoomApi() {
  let status: "lobby" | "active" = "lobby";
  let revision = 0;
  const members = new Map<Identity, Member>();
  const invites: Invite[] = [];
  const snapshotRequests: Record<Identity, number> = {
    host: 0,
    guest: 0,
    outsider: 0,
  };

  const publicInvites = () => invites.map(({ token: _token, ...invite }) => invite);
  const prerequisitesReady = () => {
    const joined = [...members.values()];
    const assigned = joined.flatMap((member) => member.character_id ? [member.character_id] : []);
    return joined.length === 2 && assigned.length === 2 &&
      new Set(assigned).size === 2 && joined.every((member) => member.ready);
  };

  const install = async (page: Page, identity: Identity, token: string) => {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      if (request.headers().authorization !== `Bearer ${token}`) {
        return apiError(route, 401, "AUTH_REQUIRED", "Bearer token required");
      }

      const pathname = new URL(request.url()).pathname;
      const method = request.method();
      const member = members.get(identity);

      if (pathname === "/api/v1/sessions/current" && method === "GET") {
        return json(route, member ? { session_id: sessionId, status, mode: "multiplayer_v1" } : null);
      }

      if (pathname === "/api/v1/sessions" && method === "POST") {
        const body = request.postDataJSON();
        expect(body).toEqual({ mode: "multiplayer_v1", script_id: "mp1-two-player" });
        if (member) return apiError(route, 409, "UNFINISHED_ROOM_EXISTS", "Room exists");
        members.set(identity, {
          member_id: `member-${identity}`,
          room_role: "host",
          character_id: null,
          ready: false,
        });
        revision += 1;
        return json(route, {
          session_id: sessionId,
          mode: "multiplayer_v1",
          status: "lobby",
          revision,
          member_id: `member-${identity}`,
          created_at: new Date().toISOString(),
        }, 201);
      }

      const acceptMatch = pathname.match(/^\/api\/v1\/session-invites\/([^/]+)\/accept$/);
      if (acceptMatch && method === "POST") {
        const invite = invites.find((candidate) => candidate.token === decodeURIComponent(acceptMatch[1]));
        if (!invite) return apiError(route, 404, "INVITE_NOT_FOUND", "Invite missing");
        if (invite.revoked) return apiError(route, 410, "INVITE_REVOKED", "Invite revoked");
        if (invite.uses_count >= invite.max_uses) return apiError(route, 410, "INVITE_EXHAUSTED", "Invite used");
        if (members.size >= 2) return apiError(route, 409, "ROOM_FULL", "Room full");
        members.set(identity, {
          member_id: `member-${identity}`,
          room_role: "player",
          character_id: null,
          ready: false,
        });
        invite.uses_count += 1;
        revision += 1;
        return json(route, {
          session_id: sessionId,
          status: "lobby",
          revision,
          member_id: `member-${identity}`,
        });
      }

      if (!member) return apiError(route, 403, "NOT_ROOM_MEMBER", "Not a member");

      if (pathname === `/api/v1/sessions/${sessionId}/snapshot` && method === "GET") {
        snapshotRequests[identity] += 1;
        const orderedMembers = [...members.values()];
        if (status === "active") {
          return json(route, {
            snapshot_version: 1,
            session_id: sessionId,
            mode: "multiplayer_v1",
            status: "active",
            revision,
            event_head_sequence: revision,
            package: { script_id: "mp1-two-player", title: "双人测试剧本", version: "1.0.0" },
            self_member_id: member.member_id,
            stage_id: "investigation",
            stage_name: "核对口供",
            phase: "read",
            suggested_discussion_minutes: 12,
            players: orderedMembers.map((candidate) => ({
              member_id: candidate.member_id,
              character_id: candidate.character_id,
              character_name: characters.find((character) => character.id === candidate.character_id)?.name,
              scene_x: candidate.character_id === "investigator" ? 1455 : 945,
              scene_y: 970,
              scene_facing: candidate.character_id === "investigator" ? "left" : "right",
              scene_moving: false,
              scene_online: true,
            })),
            read_member_ids: [],
            discussion_close_member_ids: [],
            chapters: [{
              id: `${member.character_id}-investigation`,
              title: "第一章",
              content: "只属于当前角色的测试章节。",
            }],
            public_materials: [],
            discussion_messages: [],
            settlement: null,
            hints: [],
            can_advance: false,
            can_end_incomplete: member.room_role === "host",
            ending_id: null,
          });
        }
        return json(route, {
          session_id: sessionId,
          mode: "multiplayer_v1",
          status,
          revision,
          package: { script_id: "mp1-two-player", title: "双人测试剧本", version: "1.0.0" },
          capacity: { min_players: 2, max_players: 2, joined: orderedMembers.length },
          self: member,
          members: orderedMembers,
          characters: characters.map((character) => ({
            ...character,
            assigned_member_id: orderedMembers.find((candidate) => candidate.character_id === character.id)?.member_id ?? null,
          })),
          capabilities: {
            can_invite: status === "lobby" && member.room_role === "host" && members.size < 2,
            can_assign_character: status === "lobby",
            can_ready: status === "lobby" && member.character_id !== null,
            can_start: status === "lobby" && member.room_role === "host" && prerequisitesReady(),
            can_end_incomplete: status === "lobby" && member.room_role === "host",
          },
          invites: member.room_role === "host" ? publicInvites() : [],
        });
      }

      if (pathname === `/api/v1/sessions/${sessionId}/invites` && method === "POST") {
        if (member.room_role !== "host") return apiError(route, 403, "HOST_REQUIRED", "Host required");
        const body = request.postDataJSON();
        expect(body).toEqual({ ttl_seconds: 900 });
        const number = invites.length + 1;
        const invite: Invite = {
          invite_id: `invite-${number}`,
          token: `join-token-${number}`,
          expires_at: new Date(Date.now() + 900_000).toISOString(),
          uses_count: 0,
          max_uses: 1,
          revoked: false,
        };
        invites.push(invite);
        return json(route, {
          invite_id: invite.invite_id,
          token: invite.token,
          expires_at: invite.expires_at,
        }, 201);
      }

      const revokeMatch = pathname.match(new RegExp(`^/api/v1/sessions/${sessionId}/invites/([^/]+)$`));
      if (revokeMatch && method === "DELETE") {
        if (member.room_role !== "host") return apiError(route, 403, "HOST_REQUIRED", "Host required");
        const invite = invites.find((candidate) => candidate.invite_id === decodeURIComponent(revokeMatch[1]));
        if (invite) invite.revoked = true;
        return route.fulfill({ status: 204 });
      }

      if (pathname === `/api/v1/sessions/${sessionId}/scene-presence` && method === "PUT") {
        const body = request.postDataJSON();
        expect(Object.keys(body).sort()).toEqual(["facing", "moving", "x", "y"]);
        return route.fulfill({ status: 204, body: "" });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/commands` && method === "POST") {
        const body = request.postDataJSON();
        expect(body.command_id).toMatch(/^[0-9a-f-]{36}$/i);
        if (body.expected_revision !== revision) {
          return apiError(route, 409, "REVISION_MISMATCH", "Refresh snapshot");
        }
        if (body.type === "room.assign_character") {
          const occupied = [...members.values()].some(
            (candidate) => candidate !== member && candidate.character_id === body.payload.character_id,
          );
          if (occupied) return apiError(route, 409, "CHARACTER_ALREADY_ASSIGNED", "Taken");
          member.character_id = body.payload.character_id;
          member.ready = false;
        } else if (body.type === "room.unassign_character") {
          member.character_id = null;
          member.ready = false;
        } else if (body.type === "room.ready") {
          if (!member.character_id) return apiError(route, 409, "CHARACTER_REQUIRED", "Select a character");
          member.ready = body.payload.ready;
        } else if (body.type === "room.start") {
          if (member.room_role !== "host") return apiError(route, 403, "HOST_REQUIRED", "Host required");
          if (!prerequisitesReady()) return apiError(route, 409, "PLAYERS_NOT_READY", "Players not ready");
          status = "active";
        }
        revision += 1;
        return json(route, {
          command_id: body.command_id,
          status: "accepted",
          revision,
          event_sequence: 0,
          result: { event_ids: [] },
          error: null,
          replayed: false,
        });
      }

      return apiError(route, 404, "NOT_FOUND", pathname);
    });
  };

  return { install, snapshotRequests };
}

async function createPlayerPage(
  browser: Browser,
  api: ReturnType<typeof createMockRoomApi>,
  identity: Identity,
) {
  const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
  await context.addInitScript(() => {
    Object.defineProperty(Crypto.prototype, "randomUUID", { value: undefined, configurable: true });
  });
  const token = await installAnonymousAuth(context, identity);
  const page = await context.newPage();
  const webSockets: string[] = [];
  page.on("websocket", (socket) => {
    if (!socket.url().includes("/_next/")) webSockets.push(socket.url());
  });
  await api.install(page, identity, token);
  return { context, page, webSockets };
}

test("lobby rooms retain recovery polling", async ({ browser }) => {
  const api = createMockRoomApi();
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto("/multiplayer");
    await host.page.getByRole("button", { name: "创建双人房间" }).click();
    await expect(host.page.getByRole("heading", { name: "房间大厅" })).toBeVisible();
    const snapshotCount = api.snapshotRequests.host;
    await expect.poll(
      () => api.snapshotRequests.host,
      { timeout: 4_000 },
    ).toBeGreaterThan(snapshotCount);
  } finally {
    await host.context.close();
  }
});

test("two anonymous players can join, select, ready, and atomically start without WebSocket", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createMockRoomApi();
  const host = await createPlayerPage(browser, api, "host");
  const guest = await createPlayerPage(browser, api, "guest");
  const outsider = await createPlayerPage(browser, api, "outsider");

  try {
    await host.page.goto("/multiplayer");
    await host.page.getByRole("button", { name: "创建双人房间" }).click();
    await expect(host.page).toHaveURL(new RegExp(`/play/${sessionId}/lobby$`));
    await expect(host.page.getByRole("heading", { name: "房间大厅" })).toBeVisible();
    await expect(host.page.getByTestId("player-slot-2")).toContainText("等待玩家加入");
    await expect(host.page.getByRole("button", { name: "开始游戏" })).toBeDisabled();

    await host.page.getByRole("button", { name: "创建 15 分钟邀请" }).click();
    const firstInviteUrl = await host.page.getByTestId("invite-url").textContent();
    expect(firstInviteUrl).toContain("/invite/join-token-1");

    await host.page.getByRole("button", { name: "创建 15 分钟邀请" }).click();
    await expect(host.page.getByTestId("invite-url")).toContainText("/invite/join-token-2");
    await host.page.reload();
    await expect(host.page.getByTestId("invite-url")).toContainText("/invite/join-token-2");
    await host.page.getByRole("button", { name: "复制邀请链接" }).click();
    await expect(host.page.getByRole("button", { name: "已复制" })).toBeVisible();
    await host.page.getByRole("button", { name: "撤销邀请 invite-2" }).click();

    await outsider.page.goto("/invite/join-token-2");
    await expect(outsider.page.getByRole("heading", { name: "无法加入房间" })).toBeVisible();
    await expect(outsider.page.getByRole("alert").filter({ hasText: "INVITE_REVOKED" })).toBeVisible();

    await guest.page.goto(firstInviteUrl!);
    await expect(guest.page).toHaveURL(new RegExp(`/play/${sessionId}/lobby$`));
    await expect(guest.page.getByRole("heading", { name: "房间大厅" })).toBeVisible();
    await expect(host.page.getByTestId("player-slot-2")).toContainText("玩家 2", { timeout: 5_000 });

    await host.page.getByRole("button", { name: "选择角色 侦探甲" }).click();
    await host.page.getByRole("button", { name: "取消选择角色 侦探甲" }).click();
    await host.page.getByRole("button", { name: "选择角色 侦探甲" }).click();
    await host.page.getByRole("button", { name: "准备", exact: true }).click();
    await host.page.getByRole("button", { name: "取消准备" }).click();
    await host.page.getByRole("button", { name: "准备", exact: true }).click();

    // Reload proves the browser-bound anonymous identity resumes while also taking a fresh revision.
    await guest.page.reload();
    await expect(guest.page.getByRole("heading", { name: "房间大厅" })).toBeVisible();
    await guest.page.getByRole("button", { name: "选择角色 侦探乙" }).click();
    await guest.page.getByRole("button", { name: "准备", exact: true }).click();

    await expect(host.page.getByRole("button", { name: "开始游戏" })).toBeEnabled({ timeout: 5_000 });
    await host.page.getByRole("button", { name: "开始游戏" }).click();
    await expect(host.page.locator(".mansion-demo")).toBeVisible();
    await expect(host.page.getByRole("heading", { name: "核对口供" })).toHaveCount(0);
    const scene = host.page.locator(".mansion-demo");
    const initialY = Number(await scene.getAttribute("data-player-y"));
    await host.page.keyboard.down("KeyW");
    await host.page.waitForTimeout(450);
    await host.page.keyboard.up("KeyW");
    await expect.poll(async () => Number(await scene.getAttribute("data-player-y"))).toBeLessThan(initialY);

    expect(host.webSockets).toEqual([]);
    expect(guest.webSockets).toEqual([]);
    expect(outsider.webSockets).toEqual([]);
  } finally {
    await Promise.all([host.context.close(), guest.context.close(), outsider.context.close()]);
  }
});
