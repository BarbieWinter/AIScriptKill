import { expect, test, type Browser, type BrowserContext, type Page, type Route } from "@playwright/test";

type Identity = "host" | "guest";
type InitialStatus = "lobby" | "active";

const sessionId = "88888888-8888-4888-8888-888888888888";
const members = {
  host: { member_id: "member-host", room_role: "host" as const },
  guest: { member_id: "member-guest", room_role: "player" as const },
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
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

function createClosureApi(initialStatus: InitialStatus) {
  let status: InitialStatus | "closed" = initialStatus;
  let revision = 4;
  let eventHeadSequence = 3;
  let commandCount = 0;
  let currentRoomFailureCount = 0;

  const snapshotFor = (identity: Identity) => {
    const self = members[identity];
    const packageSummary = {
      script_id: "mp1-two-player",
      title: "两份口供",
      version: "1.0.0",
    };
    if (status === "closed") {
      return {
        session_id: sessionId,
        mode: "multiplayer_v1",
        status,
        revision,
        event_head_sequence: eventHeadSequence,
        package: packageSummary,
        self_member_id: self.member_id,
        closed_at: "2026-07-27T08:00:00Z",
        review_available: false,
      };
    }
    if (status === "active") {
      return {
        snapshot_version: 1,
        session_id: sessionId,
        mode: "multiplayer_v1",
        status,
        revision,
        event_head_sequence: eventHeadSequence,
        package: packageSummary,
        self_member_id: self.member_id,
        stage_id: "investigation",
        stage_name: "核对口供",
        phase: "read",
        suggested_discussion_minutes: 8,
        players: [
          {
            member_id: members.host.member_id,
            character_id: "investigator",
            character_name: "调查员",
            scene_x: 1455,
            scene_y: 970,
            scene_facing: "left",
            scene_moving: false,
            scene_online: true,
          },
          {
            member_id: members.guest.member_id,
            character_id: "insider",
            character_name: "知情人",
            scene_x: 945,
            scene_y: 970,
            scene_facing: "right",
            scene_moving: false,
            scene_online: true,
          },
        ],
        read_member_ids: [],
        discussion_close_member_ids: [],
        chapters: [{ id: `${identity}-chapter`, title: "角色章节", content: "私有章节内容" }],
        public_materials: [],
        discussion_messages: [],
        settlement: null,
        hints: [],
        can_advance: false,
        can_end_incomplete: identity === "host",
        ending_id: null,
      };
    }
    return {
      session_id: sessionId,
      mode: "multiplayer_v1",
      status,
      revision,
      package: packageSummary,
      capacity: { min_players: 2, max_players: 2, joined: 2 },
      self: { ...self, character_id: null, ready: false },
      members: Object.values(members).map((member) => ({
        ...member,
        character_id: null,
        ready: false,
      })),
      characters: [
        {
          id: "investigator",
          name: "调查员",
          public_description: "负责核对时间线",
          assigned_member_id: null,
        },
        {
          id: "insider",
          name: "知情人",
          public_description: "熟悉值班室流程",
          assigned_member_id: null,
        },
      ],
      capabilities: {
        can_invite: identity === "host",
        can_assign_character: true,
        can_ready: false,
        can_start: false,
        can_end_incomplete: identity === "host",
      },
      invites: [],
    };
  };

  const install = async (page: Page, identity: Identity, token: string) => {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      if (request.headers().authorization !== `Bearer ${token}`) {
        return json(route, { error: { code: "AUTH_REQUIRED", message: "Auth required", details: {} } }, 401);
      }
      const pathname = new URL(request.url()).pathname;
      const method = request.method();
      if (pathname === "/api/v1/sessions/current" && method === "GET") {
        if (status === "closed") {
          currentRoomFailureCount += 1;
          return json(route, { error: { code: "TEMPORARY_FAILURE", message: "Unavailable", details: {} } }, 503);
        }
        return json(route, { session_id: sessionId, status, mode: "multiplayer_v1" });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/snapshot` && method === "GET") {
        return json(route, snapshotFor(identity));
      }
      if (pathname === `/api/v1/sessions/${sessionId}/scene-presence` && method === "PUT") {
        return route.fulfill({ status: 204, body: "" });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/commands` && method === "POST") {
        const body = request.postDataJSON();
        expect(identity).toBe("host");
        expect(body).toMatchObject({
          expected_revision: 4,
          type: "room.end_incomplete",
          payload: { reason: null },
        });
        expect(body.command_id).toMatch(/^[0-9a-f-]{36}$/i);
        commandCount += 1;
        status = "closed";
        revision = 5;
        eventHeadSequence = 4;
        return json(route, {
          command_id: body.command_id,
          status: "accepted",
          revision,
          event_sequence: eventHeadSequence,
          result: { event_ids: [] },
          error: null,
          replayed: false,
        });
      }
      return json(route, { error: { code: "NOT_FOUND", message: pathname, details: {} } }, 404);
    });
  };

  return {
    install,
    commandCount: () => commandCount,
    currentRoomFailureCount: () => currentRoomFailureCount,
  };
}

async function createPlayerPage(
  browser: Browser,
  api: ReturnType<typeof createClosureApi>,
  identity: Identity,
) {
  const context = await browser.newContext();
  const token = await installAnonymousAuth(context, identity);
  const page = await context.newPage();
  await api.install(page, identity, token);
  return { context, page };
}

for (const initialStatus of ["lobby", "active"] as const) {
  test(`host can ${initialStatus === "lobby" ? "close a lobby" : "abandon an active room"} and both players see a non-review terminal state`, async ({ browser }) => {
    const api = createClosureApi(initialStatus);
    const host = await createPlayerPage(browser, api, "host");
    const guest = await createPlayerPage(browser, api, "guest");
    const actionLabel = initialStatus === "lobby" ? "关闭房间" : "放弃本局";

    try {
      await Promise.all([
        host.page.goto(`/play/${sessionId}/lobby`),
        guest.page.goto(`/play/${sessionId}/lobby`),
      ]);
      await expect(host.page.getByRole("button", { name: actionLabel, exact: true })).toBeVisible();
      await expect(guest.page.getByRole("button", { name: actionLabel, exact: true })).toHaveCount(0);

      const roomAction = host.page.getByRole("button", { name: actionLabel, exact: true });
      await roomAction.click();
      await expect(host.page.getByRole("dialog")).toBeVisible();
      await expect(host.page.getByRole("dialog")).toContainText("不会生成结局或复盘");
      await expect.poll(() => host.page.evaluate(() => document.body.style.overflow)).toBe("hidden");
      const confirmAction = host.page.getByRole("button", { name: `确认${actionLabel}` });
      await expect(confirmAction).toBeFocused();
      await host.page.keyboard.press("Tab");
      await expect(host.page.getByRole("button", { name: "取消关闭" })).toBeFocused();
      await host.page.keyboard.press("Shift+Tab");
      await expect(confirmAction).toBeFocused();
      await host.page.keyboard.press("Escape");
      await expect(host.page.getByRole("dialog")).toHaveCount(0);
      await expect.poll(() => host.page.evaluate(() => document.body.style.overflow)).toBe("");
      await expect(roomAction).toBeFocused();
      expect(api.commandCount()).toBe(0);

      await roomAction.click();
      await host.page.getByRole("button", { name: `确认${actionLabel}` }).click();

      for (const player of [host, guest]) {
        await expect(player.page.getByRole("heading", { name: "房间已关闭" })).toBeVisible({ timeout: 5_000 });
        await expect(player.page.getByText("没有结局或复盘", { exact: false })).toBeVisible();
        await expect(player.page.getByRole("link", { name: "返回多人入口" })).toBeVisible();
      }
      expect(api.commandCount()).toBe(1);

      for (const player of [host, guest]) {
        await player.page.getByRole("link", { name: "返回多人入口" }).click();
        await expect(player.page.getByRole("button", { name: "创建双人房间" })).toBeEnabled();
      }
      await expect.poll(api.currentRoomFailureCount).toBeGreaterThan(0);
    } finally {
      await Promise.all([host.context.close(), guest.context.close()]);
    }
  });
}
