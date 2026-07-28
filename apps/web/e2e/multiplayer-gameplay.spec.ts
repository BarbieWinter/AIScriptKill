import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
  type Page,
  type Route,
} from "@playwright/test";

import type { CompletedReviewV1, GameplaySnapshotV1 } from "@/lib/multiplayer/types";
import gameplayContractJson from "./fixtures/multiplayer-gameplay-contract.json";

type Identity = "host" | "guest";
type ScenePresence = {
  x: number;
  y: number;
  facing: "left" | "right";
  moving: boolean;
};
type PresencePayload = ScenePresence & Record<string, unknown>;
type ContractTransition = {
  from: string;
  to: string;
  identity: Identity;
  type: string;
  payload: Record<string, unknown>;
  revision: number;
  event_sequence: number;
};
type GameplayContract = {
  fixture_version: 1;
  session_id: string;
  identities: Record<Identity, string>;
  hint_levels: string[];
  initial_state: string;
  states: Record<string, Record<Identity, GameplaySnapshotV1>>;
  transitions: ContractTransition[];
  reviews: Record<Identity, CompletedReviewV1>;
};

const gameplayContract = gameplayContractJson as GameplayContract;
const sessionId = gameplayContract.session_id;
const hintLevels = gameplayContract.hint_levels;
const members = {
  host: {
    memberId: gameplayContract.identities.host,
    characterId: "investigator",
    characterName: "调查员",
  },
  guest: {
    memberId: gameplayContract.identities.guest,
    characterId: "insider",
    characterName: "知情人",
  },
} as const;

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function samePayload(actual: Record<string, unknown>, expected: Record<string, unknown>) {
  const actualKeys = Object.keys(actual).sort();
  const expectedKeys = Object.keys(expected).sort();
  return JSON.stringify(actualKeys) === JSON.stringify(expectedKeys)
    && expectedKeys.every((key) => actual[key] === expected[key]);
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

function createGameplayApi(initialState = gameplayContract.initial_state) {
  let stateKey = initialState;
  let messageFailures = 0;
  let revisionFailures = 0;
  let publicMaterialsVisible = true;
  const snapshotFailures: Record<Identity, number> = { host: 0, guest: 0 };
  const reviewFailures: Record<Identity, number> = { host: 0, guest: 0 };
  let discussionMessageId: string | null = null;
  const presence = new Map<Identity, ScenePresence>([
    ["host", { x: 1455, y: 970, facing: "left", moving: false }],
    ["guest", { x: 945, y: 970, facing: "right", moving: false }],
  ]);
  const presenceBodies: Array<{ identity: Identity; body: PresencePayload }> = [];
  const commandBodies: Array<{ identity: Identity; type: string; payload: Record<string, unknown> }> = [];
  const reviewRequests: Identity[] = [];

  const snapshotFor = (identity: Identity) => {
    const snapshot = clone(gameplayContract.states[stateKey][identity]);
    if (discussionMessageId && snapshot.discussion_messages.length > 0) {
      snapshot.discussion_messages[0].message_id = discussionMessageId;
    }
    if (!publicMaterialsVisible) snapshot.public_materials = [];
    snapshot.players = snapshot.players.map((player) => {
      const playerIdentity = player.member_id === members.host.memberId ? "host" : "guest";
      const pose = presence.get(playerIdentity);
      return {
        ...player,
        scene_x: pose?.x ?? null,
        scene_y: pose?.y ?? null,
        scene_facing: pose?.facing ?? null,
        scene_moving: pose?.moving ?? false,
        scene_online: pose !== undefined,
      };
    });
    return snapshot;
  };

  const rejectCommand = (route: Route, commandId: string, code: string, message: string) => {
    const snapshot = snapshotFor("host");
    return json(route, {
      command_id: commandId,
      status: "rejected",
      revision: snapshot.revision,
      event_sequence: snapshot.event_head_sequence,
      result: null,
      error: { code, message, details: {} },
      replayed: false,
    });
  };

  const install = async (page: Page, identity: Identity, token: string) => {
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      if (request.headers().authorization !== `Bearer ${token}`) {
        return json(route, { error: { code: "AUTH_REQUIRED", message: "Bearer token required", details: {} } }, 401);
      }
      const pathname = new URL(request.url()).pathname;
      const method = request.method();

      if (pathname === `/api/v1/sessions/${sessionId}/snapshot` && method === "GET") {
        if (snapshotFailures[identity] > 0) {
          snapshotFailures[identity] -= 1;
          return json(route, { error: { code: "TEMPORARY_FAILURE", message: "Temporary snapshot failure", details: {} } }, 500);
        }
        return json(route, snapshotFor(identity));
      }
      if (pathname === "/api/v1/sessions/current" && method === "GET") {
        const snapshot = snapshotFor(identity);
        return json(route, snapshot.status === "active"
          ? { session_id: sessionId, status: "active", mode: "multiplayer_v1" }
          : null);
      }
      if (pathname === `/api/v1/sessions/${sessionId}/review` && method === "GET") {
        reviewRequests.push(identity);
        if (snapshotFor(identity).status !== "completed") {
          return json(route, { error: { code: "SESSION_NOT_COMPLETED", message: "Review is unavailable", details: {} } }, 409);
        }
        if (reviewFailures[identity] > 0) {
          reviewFailures[identity] -= 1;
          return json(route, { error: { code: "TEMPORARY_FAILURE", message: "Temporary review failure", details: {} } }, 500);
        }
        return json(route, gameplayContract.reviews[identity]);
      }
      if (pathname === `/api/v1/sessions/${sessionId}/scene-presence` && method === "PUT") {
        const body = request.postDataJSON() as PresencePayload;
        expect(Object.keys(body).sort()).toEqual(["facing", "moving", "x", "y"]);
        expect(body).not.toHaveProperty("member_id");
        expect(body).not.toHaveProperty("character_id");
        presenceBodies.push({ identity, body });
        presence.set(identity, { x: body.x, y: body.y, facing: body.facing, moving: body.moving });
        return route.fulfill({ status: 204, body: "" });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/commands` && method === "POST") {
        const body = request.postDataJSON() as {
          command_id: string;
          expected_revision: number;
          type: string;
          payload: Record<string, unknown>;
        };
        expect(body.command_id).toMatch(/^[0-9a-f-]{36}$/i);
        commandBodies.push({ identity, type: body.type, payload: body.payload });
        const current = snapshotFor(identity);
        if (revisionFailures > 0) {
          revisionFailures -= 1;
          return rejectCommand(route, body.command_id, "REVISION_MISMATCH", "Refresh snapshot");
        }
        if (body.expected_revision !== current.revision) {
          return rejectCommand(route, body.command_id, "REVISION_MISMATCH", "Refresh snapshot");
        }

        if (body.type === "discussion.send_message") {
          const transition = gameplayContract.transitions.find((candidate) => (
            candidate.from === stateKey
            && candidate.identity === identity
            && candidate.type === body.type
            && candidate.payload.stage_id === body.payload.stage_id
            && candidate.payload.text === body.payload.text
          ));
          if (!transition || typeof body.payload.message_id !== "string") {
            return rejectCommand(route, body.command_id, "PHASE_MISMATCH", "Wrong phase");
          }
          expect(body.payload.message_id).toMatch(/^[0-9a-f-]{36}$/i);
          if (messageFailures > 0) {
            messageFailures -= 1;
            return rejectCommand(route, body.command_id, "TEMPORARY_FAILURE", "Message send failed");
          }
          discussionMessageId = body.payload.message_id;
          stateKey = transition.to;
          return json(route, {
            command_id: body.command_id,
            status: "accepted",
            revision: transition.revision,
            event_sequence: transition.event_sequence,
            result: { event_ids: [] },
            error: null,
            replayed: false,
          });
        }

        const transition = gameplayContract.transitions.find((candidate) => (
          candidate.from === stateKey
          && candidate.identity === identity
          && candidate.type === body.type
          && samePayload(body.payload, candidate.payload)
        ));
        if (!transition) {
          return rejectCommand(route, body.command_id, "PHASE_MISMATCH", "Wrong phase");
        }
        stateKey = transition.to;
        return json(route, {
          command_id: body.command_id,
          status: "accepted",
          revision: transition.revision,
          event_sequence: transition.event_sequence,
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
    failNextSnapshots(identity: Identity, count = 3) {
      snapshotFailures[identity] = count;
    },
    restoreSnapshots(identity: Identity) {
      snapshotFailures[identity] = 0;
    },
    failNextMessage() {
      messageFailures = 1;
    },
    rejectNextRevision() {
      revisionFailures = 1;
    },
    failNextReviews(identity: Identity, count = 3) {
      reviewFailures[identity] = count;
    },
    hidePublicMaterials() {
      publicMaterialsVisible = false;
    },
    commandBodies,
    presenceBodies,
    reviewRequests,
  };
}

async function createPlayerPage(
  browser: Browser,
  api: ReturnType<typeof createGameplayApi>,
  identity: Identity,
  contextOptions: BrowserContextOptions = {},
) {
  const context = await browser.newContext(contextOptions);
  const token = await installAnonymousAuth(context, identity);
  const page = await context.newPage();
  const webSockets: string[] = [];
  page.on("websocket", (socket) => {
    if (!socket.url().includes("/_next/")) webSockets.push(socket.url());
  });
  await api.install(page, identity, token);
  return { context, page, webSockets };
}

async function expectScenePhase(page: Page, stageName: string, phaseName: string) {
  await expect(page.locator(".mansion-demo")).toBeVisible({ timeout: 8_000 });
  const sceneHelpDismiss = page.getByRole("button", { name: "知道了" });
  if (await sceneHelpDismiss.isVisible()) await sceneHelpDismiss.click();
  await expect(page.locator(".demo-objective-card").getByText(
    `当前阶段 · ${stageName} · ${phaseName}`,
    { exact: true },
  )).toBeVisible({ timeout: 8_000 });
}

async function openChaptersAndConfirm(page: Page) {
  await page.getByRole("button", { name: "角色章" }).click();
  await page.getByRole("button", { name: "我已读完" }).click();
}

async function confirmDiscussionClose(host: Page, guest: Page) {
  await host.getByRole("button", { name: "打开讨论" }).click();
  await guest.getByRole("button", { name: "打开讨论" }).click();
  await host.getByRole("button", { name: "确认结束讨论" }).click();
  await expect(guest.getByText("1/2 位玩家确认结束", { exact: true })).toBeVisible({ timeout: 8_000 });
  await guest.getByRole("button", { name: "确认结束讨论" }).click();
}

async function revealAllHints(host: Page, guest: Page) {
  await host.getByRole("button", { name: "打开协作提示" }).click();
  await guest.getByRole("button", { name: "打开协作提示" }).click();
  for (const [index, hintText] of hintLevels.entries()) {
    const level = index + 1;
    await host.getByRole("button", { name: `请求第 ${level} 级提示` }).click();
    await guest.getByRole("button", { name: `同意公开第 ${level} 级提示` }).click();
    await expect(host.getByText(hintText)).toBeVisible({ timeout: 8_000 });
    await expect(guest.getByText(hintText)).toBeVisible({ timeout: 8_000 });
  }
  await host.getByRole("button", { name: "关闭" }).click();
  await guest.getByRole("button", { name: "关闭" }).click();
}

test("private chapters and public materials remain participant-safe in the movable scene", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createGameplayApi();
  const host = await createPlayerPage(browser, api, "host");
  const guest = await createPlayerPage(browser, api, "guest");
  const hostSnapshot = gameplayContract.states.investigation_read.host;
  const guestSnapshot = gameplayContract.states.investigation_read.guest;

  try {
    await Promise.all([
      host.page.goto(`/play/${sessionId}/lobby`),
      guest.page.goto(`/play/${sessionId}/lobby`),
    ]);
    await expectScenePhase(host.page, "核对口供", "阅读角色信息");
    await expectScenePhase(guest.page, "核对口供", "阅读角色信息");

    const publicArchiveEntry = host.page.getByRole("button", { name: "打开公开档案" });
    await publicArchiveEntry.click();
    await expect(host.page.getByRole("heading", { name: "公开档案" })).toBeVisible();
    await expect(host.page.getByText(hostSnapshot.public_materials[0].title)).toBeVisible();
    api.hidePublicMaterials();
    await expect(host.page.getByRole("button", { name: "打开公开档案" })).toHaveCount(0, { timeout: 8_000 });
    await expect(host.page.getByRole("heading", { name: "公开档案" })).toHaveCount(0);
    await expect(host.page.getByRole("complementary", { name: "双人进度" })).toBeFocused();

    const hostScene = host.page.locator(".mansion-demo");
    const guestScene = guest.page.locator(".mansion-demo");
    const hostLocal = host.page.locator('[data-character-id="self-investigator"]');
    const guestLocal = guest.page.locator('[data-character-id="self-insider"]');
    const hostOnGuest = guest.page.locator(`[data-character-id="member-${members.host.memberId}"]`);
    const guestOnHost = host.page.locator(`[data-character-id="member-${members.guest.memberId}"]`);
    await expect(hostLocal).toHaveAttribute("data-outfit", "long-coat");
    await expect(guestLocal).toHaveAttribute("data-outfit", "soft-jacket");
    await expect(hostOnGuest).toContainText("调查员");
    await expect(guestOnHost).toContainText("知情人");

    const initialHostX = Number(await hostScene.getAttribute("data-player-x"));
    const initialHostRemoteX = Number(await hostOnGuest.getAttribute("data-scene-x"));
    await host.page.keyboard.down("KeyD");
    await host.page.waitForTimeout(650);
    await host.page.keyboard.up("KeyD");
    await expect.poll(async () => Number(await hostScene.getAttribute("data-player-x"))).toBeGreaterThan(initialHostX);
    await expect.poll(
      async () => Number(await hostOnGuest.getAttribute("data-scene-x")),
      { timeout: 8_000 },
    ).toBeGreaterThan(initialHostRemoteX);

    const initialGuestY = Number(await guestScene.getAttribute("data-player-y"));
    await guest.page.keyboard.down("KeyW");
    await guest.page.waitForTimeout(650);
    await guest.page.keyboard.up("KeyW");
    await expect.poll(async () => Number(await guestScene.getAttribute("data-player-y"))).toBeLessThan(initialGuestY);
    expect(api.presenceBodies.some(({ identity }) => identity === "host")).toBe(true);
    expect(api.presenceBodies.some(({ identity }) => identity === "guest")).toBe(true);

    await host.page.getByRole("button", { name: "角色章" }).click();
    await guest.page.getByRole("button", { name: "角色章" }).click();
    await expect(host.page.getByText(hostSnapshot.chapters[0].content)).toBeVisible();
    await expect(host.page.getByText(guestSnapshot.chapters[0].content)).toHaveCount(0);
    await expect(guest.page.getByText(guestSnapshot.chapters[0].content)).toBeVisible();
    await expect(guest.page.getByText(hostSnapshot.chapters[0].content)).toHaveCount(0);
    await host.page.getByRole("button", { name: "我已读完" }).click();
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    expect(host.webSockets).toEqual([]);
    expect(guest.webSockets).toEqual([]);
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});

test("revealed hints stay readable and Sheet keeps keyboard focus contained", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createGameplayApi();
  const host = await createPlayerPage(browser, api, "host");
  const guest = await createPlayerPage(browser, api, "guest");

  try {
    await Promise.all([
      host.page.goto(`/play/${sessionId}/lobby`),
      guest.page.goto(`/play/${sessionId}/lobby`),
    ]);
    await expectScenePhase(host.page, "核对口供", "阅读角色信息");
    await expectScenePhase(guest.page, "核对口供", "阅读角色信息");
    await openChaptersAndConfirm(host.page);
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    await openChaptersAndConfirm(guest.page);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await host.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "关闭" }).click();

    const fixedHintEntry = host.page.getByRole("button", { name: "打开协作提示" });
    await fixedHintEntry.focus();
    await host.page.keyboard.press("Enter");
    const hintDialog = host.page.getByRole("dialog", { name: "协作提示" });
    const hintCloseButton = hintDialog.getByRole("button", { name: "关闭" });
    await expect(hintCloseButton).toBeFocused();
    await host.page.locator(".demo-hud-actions button").first().focus();
    await host.page.keyboard.press("Tab");
    await expect(hintCloseButton).toBeFocused();
    await host.page.keyboard.press("Escape");
    await expect(fixedHintEntry).toBeFocused();

    await revealAllHints(host.page, guest.page);
    await host.page.reload();
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await host.page.getByRole("button", { name: "打开协作提示" }).click();
    await expect(host.page.getByText(hintLevels[2])).toBeVisible();
    await host.page.getByRole("button", { name: "关闭" }).click();

    await host.page.getByRole("button", { name: "打开讨论" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    await host.page.getByRole("button", { name: "确认结束讨论" }).click();
    await expect(guest.page.getByText("1/2 位玩家确认结束", { exact: true })).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "关闭" }).click();
    await host.page.getByRole("button", { name: "打开协作提示" }).click();
    await expect(host.page.getByRole("dialog", { name: "协作提示" })).toBeVisible();
    await guest.page.getByRole("button", { name: "确认结束讨论" }).click();
    await expectScenePhase(host.page, "核对口供", "提交判断");
    await expect(host.page.getByRole("dialog", { name: "协作提示" })).toHaveCount(0);
    await expect(guest.page.getByRole("dialog", { name: "双人公开讨论" })).toHaveCount(0);
    await expect(host.page.getByRole("complementary", { name: "双人进度" })).toBeFocused();
    await expect(guest.page.getByRole("complementary", { name: "双人进度" })).toBeFocused();
    await host.page.getByRole("button", { name: "打开协作提示" }).click();
    await expect(host.page.getByText(hintLevels[2])).toBeVisible();
    await expect(host.page.getByRole("button", { name: /请求第|同意公开第/ })).toHaveCount(0);
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});

test("synchronization and message failures recover without closing the discussion Sheet", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createGameplayApi("investigation_discuss");
  const host = await createPlayerPage(browser, api, "host");
  const guest = await createPlayerPage(browser, api, "guest");

  try {
    await Promise.all([
      host.page.goto(`/play/${sessionId}/lobby`),
      guest.page.goto(`/play/${sessionId}/lobby`),
    ]);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    api.failNextSnapshots("host", 20);
    const syncWarning = host.page.getByText("同步暂时中断，正在显示上次成功状态。");
    await expect(syncWarning).toBeVisible({ timeout: 15_000 });
    api.restoreSnapshots("host");
    await host.page.getByRole("button", { name: "重试同步" }).click();
    await expect(syncWarning).toHaveCount(0, { timeout: 8_000 });

    await host.page.getByRole("button", { name: "打开讨论" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    const messageInput = host.page.getByRole("textbox", { name: "讨论消息" });
    const sendMessageButton = host.page.getByRole("button", { name: "发送讨论消息" });
    await messageInput.fill("门锁没有损坏。");
    const messageCommandsBeforeConflict = api.commandBodies.filter(
      ({ type }) => type === "discussion.send_message",
    ).length;
    api.rejectNextRevision();
    await sendMessageButton.click();
    await expect(messageInput).toHaveValue("门锁没有损坏。");
    await expect.poll(
      () => api.commandBodies.filter(({ type }) => type === "discussion.send_message").length,
    ).toBe(messageCommandsBeforeConflict + 1);
    await host.page.waitForTimeout(1_000);
    expect(api.commandBodies.filter(({ type }) => type === "discussion.send_message")).toHaveLength(
      messageCommandsBeforeConflict + 1,
    );

    api.failNextMessage();
    await sendMessageButton.click();
    await expect(messageInput).toHaveValue("门锁没有损坏。");
    await expect(host.page.getByRole("main").getByText("Message send failed", { exact: true })).toBeVisible();
    const discussionDialog = host.page.getByRole("dialog", { name: "双人公开讨论" });
    const dialogCloseButton = discussionDialog.getByRole("button", { name: "关闭" });
    const syncButton = discussionDialog.getByRole("button", { name: "同步" });
    const closeDiscussionButton = discussionDialog.getByRole("button", { name: "确认结束讨论" });
    await dialogCloseButton.focus();
    await host.page.keyboard.press("Tab");
    await expect(syncButton).toBeFocused();
    await closeDiscussionButton.focus();
    await host.page.keyboard.press("Tab");
    await expect(dialogCloseButton).toBeFocused();
    await host.page.keyboard.press("Shift+Tab");
    await expect(closeDiscussionButton).toBeFocused();
    await host.page.getByRole("button", { name: "发送讨论消息" }).click();
    await expect(messageInput).toHaveValue("");
    await expect(guest.page.getByText("门锁没有损坏。")).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "关闭" }).click();
    await host.page.getByRole("button", { name: "打开协作提示" }).click();
    await guest.page.getByRole("button", { name: "打开协作提示" }).click();
    await host.page.getByRole("button", { name: "请求第 1 级提示" }).click();
    await guest.page.getByRole("button", { name: "同意公开第 1 级提示" }).click();
    await expect(host.page.getByText(hintLevels[0])).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    await expect(guest.page.getByText("门锁没有损坏。")).toBeVisible();
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});

test("two players complete the authored game and open participant-safe review", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createGameplayApi();
  const host = await createPlayerPage(browser, api, "host");
  const guest = await createPlayerPage(browser, api, "guest");

  try {
    await Promise.all([
      host.page.goto(`/play/${sessionId}/lobby`),
      guest.page.goto(`/play/${sessionId}/lobby`),
    ]);
    await expectScenePhase(host.page, "核对口供", "阅读角色信息");
    await expectScenePhase(guest.page, "核对口供", "阅读角色信息");
    await openChaptersAndConfirm(host.page);
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    await openChaptersAndConfirm(guest.page);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await host.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "关闭" }).click();
    await revealAllHints(host.page, guest.page);
    await confirmDiscussionClose(host.page, guest.page);
    await expectScenePhase(host.page, "核对口供", "提交判断");

    const investigation = gameplayContract.states.investigation_settle.host.settlement!;
    await host.page.getByRole("button", { name: "打开判断" }).click();
    await guest.page.getByRole("button", { name: "打开判断" }).click();
    const settlementDialog = host.page.getByRole("dialog", { name: "圆桌判断" });
    const settlementClose = settlementDialog.getByRole("button", { name: "关闭" });
    const firstSettlementRadio = settlementDialog.getByRole("radio").first();
    await settlementClose.focus();
    await host.page.keyboard.press("Tab");
    await expect(firstSettlementRadio).toBeFocused();
    await host.page.keyboard.press("Tab");
    await expect(settlementClose).toBeFocused();
    await host.page.getByText(investigation.options[0].text, { exact: true }).click();
    await host.page.getByRole("button", { name: "确认选择" }).click();
    await expect(guest.page.getByText("1/2 位玩家已提交", { exact: true })).toBeVisible({ timeout: 8_000 });
    await guest.page.getByText(investigation.options[1].text, { exact: true }).click();
    await guest.page.getByRole("button", { name: "确认选择" }).click();
    await expect(host.page.getByTestId("revealed-ballots")).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "进入下一阶段" }).click();
    await expectScenePhase(host.page, "共同终判", "阅读角色信息");
    await expect(host.page.getByRole("button", { name: "打开公开档案" })).toBeVisible();

    await openChaptersAndConfirm(host.page);
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    await openChaptersAndConfirm(guest.page);
    await expectScenePhase(host.page, "共同终判", "公开讨论");
    await host.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "关闭" }).click();
    await confirmDiscussionClose(host.page, guest.page);
    await expectScenePhase(host.page, "共同终判", "提交判断");

    const finalSettlement = gameplayContract.states.final_settle.host.settlement!;
    const finalChoice = finalSettlement.options.find((option) => option.id === "timeline-conflict")!;
    await host.page.getByRole("button", { name: "打开判断" }).click();
    await guest.page.getByRole("button", { name: "打开判断" }).click();
    await host.page.getByText(finalChoice.text, { exact: true }).click();
    await host.page.getByRole("button", { name: "确认选择" }).click();
    await expect(guest.page.getByText("1/2 位玩家已提交", { exact: true })).toBeVisible({ timeout: 8_000 });
    expect(api.reviewRequests).toEqual([]);
    await guest.page.getByText(finalChoice.text, { exact: true }).click();
    await guest.page.getByRole("button", { name: "确认选择" }).click();
    await expect(host.page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({ timeout: 8_000 });
    await expect(guest.page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("button", { name: "关闭" }).click();

    api.failNextReviews("host");
    await host.page.getByRole("button", { name: "打开复盘" }).click();
    await expect(host.page.getByText("Temporary review failure", { exact: true })).toBeVisible({ timeout: 12_000 });
    await host.page.getByRole("button", { name: "重新加载复盘" }).click();
    await expect(host.page.getByRole("heading", { name: gameplayContract.reviews.host.ending.name })).toBeVisible({ timeout: 8_000 });
    await guest.page.getByRole("button", { name: "打开复盘" }).click();
    await expect(guest.page.getByRole("heading", { name: gameplayContract.reviews.guest.ending.name })).toBeVisible({ timeout: 8_000 });
    expect(host.webSockets).toEqual([]);
    expect(guest.webSockets).toEqual([]);
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});

test("mobile touch controls and fixed multiplayer entries stay actionable", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createGameplayApi();
  const host = await createPlayerPage(browser, api, "host", {
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  const guest = await createPlayerPage(browser, api, "guest");

  try {
    await Promise.all([
      host.page.goto(`/play/${sessionId}/lobby`),
      guest.page.goto(`/play/${sessionId}/lobby`),
    ]);
    await expectScenePhase(host.page, "核对口供", "阅读角色信息");
    await expectScenePhase(guest.page, "核对口供", "阅读角色信息");
    const scene = host.page.locator(".mansion-demo");
    const initialX = Number(await scene.getAttribute("data-player-x"));
    const right = host.page.getByRole("button", { name: "向右" });
    await right.dispatchEvent("pointerdown", { pointerId: 1, pointerType: "touch", isPrimary: true });
    await host.page.waitForTimeout(500);
    await right.dispatchEvent("pointerup", { pointerId: 1, pointerType: "touch", isPrimary: true });
    await expect.poll(async () => Number(await scene.getAttribute("data-player-x"))).toBeGreaterThan(initialX);

    await host.page.getByRole("button", { name: "打开公开档案" }).click();
    const archiveDialog = host.page.getByRole("dialog", { name: "公开档案" });
    await expect(archiveDialog).toBeInViewport();
    await archiveDialog.getByRole("button", { name: "关闭" }).click();
    await host.page.getByRole("button", { name: "角色章" }).click();
    await host.page.getByRole("button", { name: "我已读完" }).click();
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    await guest.page.getByRole("button", { name: "角色章" }).click();
    await guest.page.getByRole("button", { name: "我已读完" }).click();
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await host.page.getByRole("button", { name: "关闭" }).click();
    await host.page.getByRole("button", { name: "打开协作提示" }).click();
    await expect(host.page.getByRole("dialog", { name: "协作提示" })).toBeInViewport();
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});
