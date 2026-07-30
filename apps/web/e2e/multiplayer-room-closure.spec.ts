import { expect, test, type Browser, type BrowserContext, type Page, type Route } from "@playwright/test";

type Identity = "host" | "guest";
type InitialStatus = "lobby" | "active" | "closed";

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
  const commandReceipts = new Map<string, unknown>();

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
      if (
        pathname.startsWith(`/api/v1/sessions/${sessionId}/commands/`)
        && method === "GET"
      ) {
        const commandId = decodeURIComponent(pathname.split("/").at(-1) ?? "");
        const receipt = commandReceipts.get(commandId);
        if (!receipt) {
          return json(route, { error: { code: "COMMAND_NOT_FOUND", message: "Receipt missing", details: {} } }, 404);
        }
        return json(route, receipt);
      }
      if (pathname === `/api/v1/sessions/${sessionId}/snapshot` && method === "GET") {
        return json(route, snapshotFor(identity));
      }
      if (pathname === `/api/v1/sessions/${sessionId}/scene-presence` && method === "PUT") {
        return route.fulfill({ status: 204, body: "" });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/commands` && method === "POST") {
        const body = request.postDataJSON();
        const existingReceipt = commandReceipts.get(body.command_id) as { status?: string } | undefined;
        if (existingReceipt?.status === "processing") {
          return json(route, {
            error: {
              code: "COMMAND_IN_PROGRESS",
              message: "Command is still processing",
              details: {},
            },
          }, 409);
        }
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
    setProcessingReceipt(commandId: string) {
      commandReceipts.set(commandId, {
        command_id: commandId,
        status: "processing",
        revision,
        event_sequence_from: null,
        event_sequence_to: null,
        result: null,
        error_code: null,
        error_details: {},
      });
    },
    setAcceptedReceipt(commandId: string) {
      const acceptedRevision = revision + 1;
      const acceptedEventSequence = eventHeadSequence + 1;
      commandReceipts.set(commandId, {
        command_id: commandId,
        status: "succeeded",
        revision: acceptedRevision,
        event_sequence_from: acceptedEventSequence,
        event_sequence_to: acceptedEventSequence,
        result: {
          command_id: commandId,
          status: "accepted",
          revision: acceptedRevision,
          event_sequence: acceptedEventSequence,
          result: { event_ids: [] },
          error: null,
          replayed: false,
        },
        error_code: null,
        error_details: {},
      });
    },
    setRejectedReceipt(commandId: string) {
      commandReceipts.set(commandId, {
        command_id: commandId,
        status: "rejected",
        revision,
        event_sequence_from: null,
        event_sequence_to: null,
        result: null,
        error_code: "ROOM_CLOSED",
        error_details: {
          command_result: {
            command_id: commandId,
            status: "rejected",
            revision,
            event_sequence: 0,
            result: null,
            error: {
              code: "ROOM_CLOSED",
              message: "多人房间已经关闭",
              details: { closed_by: { role: "host", automatic: true } },
            },
            replayed: false,
          },
        },
      });
    },
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
  return { context, page, token };
}

test("host cannot abandon an active room while a gameplay command is unresolved", async ({ browser }) => {
  const api = createClosureApi("active");
  const host = await createPlayerPage(browser, api, "host");
  const commandId = "99999999-9999-4999-8999-999999999999";
  api.setProcessingReceipt(commandId);
  const serializedEnvelope = JSON.stringify({
    command_id: commandId,
    expected_revision: 4,
    type: "stage.confirm_read",
    payload: { stage_id: "investigation" },
  });
  await host.context.addInitScript(({ key, value }) => {
    window.localStorage.setItem(key, JSON.stringify(value));
  }, {
    key: `mp3:pending-room-command:v1:${sessionId}:${members.host.member_id}`,
    value: {
      version: 1,
      session_id: sessionId,
      member_id: members.host.member_id,
      replay_lease: null,
      serialized_envelope: serializedEnvelope,
    },
  });

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    const abandonButton = host.page.getByRole("button", { name: "放弃本局", exact: true });
    await expect(abandonButton).toBeVisible();
    await abandonButton.click();
    await host.page.getByRole("button", { name: "确认放弃本局" }).click();

    const dialog = host.page.getByRole("dialog");
    await expect(dialog.getByRole("alert")).toContainText("上一条命令仍在恢复");
    await expect(dialog.getByRole("alert")).toContainText("COMMAND_IN_PROGRESS");
    expect(api.commandCount()).toBe(0);
    await expect(host.page.getByRole("heading", { name: "房间已关闭" })).toHaveCount(0);
  } finally {
    await host.context.close();
  }
});

test("a guest pending command reaches terminal recovery after the host closes the room", async ({ browser }) => {
  const api = createClosureApi("closed");
  const guest = await createPlayerPage(browser, api, "guest");
  const commandId = "77777777-7777-4777-8777-777777777777";
  const storageKey = `mp3:pending-room-command:v1:${sessionId}:${members.guest.member_id}`;
  const serializedEnvelope = JSON.stringify({
    command_id: commandId,
    expected_revision: 4,
    type: "stage.confirm_read",
    payload: { stage_id: "investigation" },
  });
  api.setRejectedReceipt(commandId);
  await guest.context.addInitScript(({ key, value }) => {
    window.localStorage.setItem(key, JSON.stringify(value));
  }, {
    key: storageKey,
    value: {
      version: 1,
      session_id: sessionId,
      member_id: members.guest.member_id,
      replay_lease: null,
      serialized_envelope: serializedEnvelope,
    },
  });

  try {
    await guest.page.goto(`/play/${sessionId}/lobby`);
    await expect(guest.page.getByRole("heading", { name: "房间已关闭" })).toBeVisible();
    const recoveryStatus = guest.page.getByTestId("command-recovery-status");
    await expect(recoveryStatus).toContainText("命令已拒绝", { timeout: 8_000 });
    await expect(recoveryStatus).toContainText("多人房间已经关闭");
    await expect.poll(() => guest.page.evaluate(
      (key) => window.localStorage.getItem(key),
      storageKey,
    )).toBeNull();
    await expect(recoveryStatus.getByRole("button", { name: "重试" })).toHaveCount(0);
    expect(api.commandCount()).toBe(0);
  } finally {
    await guest.context.close();
  }
});

test("closed accepted recovery preserves acceptance when snapshot reconciliation fails", async ({ browser }) => {
  const api = createClosureApi("closed");
  const guest = await createPlayerPage(browser, api, "guest");
  const commandId = "55555555-5555-4555-8555-555555555555";
  const storageKey = `mp3:pending-room-command:v1:${sessionId}:${members.guest.member_id}`;
  api.setAcceptedReceipt(commandId);
  await guest.context.addInitScript(({ key, value }) => {
    window.localStorage.setItem(key, JSON.stringify(value));
  }, {
    key: storageKey,
    value: {
      version: 1,
      session_id: sessionId,
      member_id: members.guest.member_id,
      replay_lease: null,
      serialized_envelope: JSON.stringify({
        command_id: commandId,
        expected_revision: 4,
        type: "stage.confirm_read",
        payload: { stage_id: "investigation" },
      }),
    },
  });

  try {
    await guest.page.goto(`/play/${sessionId}/lobby`);
    const recoveryStatus = guest.page.getByTestId("command-recovery-status");
    await expect(recoveryStatus).toContainText("命令已接受，但终态同步失败", {
      timeout: 8_000,
    });
    await expect(recoveryStatus).toContainText("权威终态尚未覆盖已接受命令");
    expect(await guest.page.evaluate(
      (key) => window.localStorage.getItem(key),
      storageKey,
    )).not.toBeNull();
  } finally {
    await guest.context.close();
  }
});

test("closed recovery clears stale UI when another tab removes the terminal record", async ({ browser }) => {
  const api = createClosureApi("closed");
  const guest = await createPlayerPage(browser, api, "guest");
  const peer = await guest.context.newPage();
  await api.install(peer, "guest", guest.token);
  const commandId = "66666666-6666-4666-8666-666666666666";
  const storageKey = `mp3:pending-room-command:v1:${sessionId}:${members.guest.member_id}`;
  const record = {
    version: 1,
    session_id: sessionId,
    member_id: members.guest.member_id,
    replay_lease: null,
    serialized_envelope: JSON.stringify({
      command_id: commandId,
      expected_revision: 4,
      type: "stage.confirm_read",
      payload: { stage_id: "investigation" },
    }),
  };
  api.setProcessingReceipt(commandId);

  try {
    await peer.goto("/multiplayer");
    await peer.evaluate(({ key, value }) => {
      window.localStorage.setItem(key, JSON.stringify(value));
    }, { key: storageKey, value: record });
    await guest.page.goto(`/play/${sessionId}/lobby`);
    const recoveryStatus = guest.page.getByTestId("command-recovery-status");
    await expect(recoveryStatus).toContainText("正在确认上一条命令", { timeout: 8_000 });

    await peer.evaluate((key) => window.localStorage.removeItem(key), storageKey);
    await expect(recoveryStatus).toHaveCount(0, { timeout: 3_000 });
  } finally {
    await guest.context.close();
  }
});

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
