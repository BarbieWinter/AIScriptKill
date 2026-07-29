import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type BrowserContextOptions,
  type Page,
  type Route,
} from "@playwright/test";

import type {
  CompletedReviewV1,
  GameplayDiscussionMessage,
  GameplaySnapshotV1,
} from "@/lib/multiplayer/types";
import gameplayContractJson from "./fixtures/multiplayer-gameplay-contract.json";

type Identity = "host" | "guest";
type ScenePresence = {
  x: number;
  y: number;
  facing: "left" | "right";
  moving: boolean;
};
type PresencePayload = ScenePresence & Record<string, unknown>;
type SnapshotHold = { promise: Promise<void>; release: () => void };
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
  let signupRequests = 0;
  await context.route("**/auth/v1/signup", async (route) => {
    signupRequests += 1;
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
  return {
    token,
    getSignupRequests: () => signupRequests,
  };
}

function createGameplayApi(initialState = gameplayContract.initial_state) {
  if (!gameplayContract.states[initialState]) {
    throw new Error(`Unknown gameplay contract state: ${initialState}`);
  }
  let stateKey = initialState;
  let messageFailures = 0;
  let revisionFailures = 0;
  let publicMaterialsVisible = true;
  let settlementVisible = true;
  let holdNextPresence = false;
  let releaseHeldPresence: (() => void) | null = null;
  const snapshotFailures: Record<Identity, number> = { host: 0, guest: 0 };
  const snapshotRequests: Record<Identity, number> = { host: 0, guest: 0 };
  const reviewFailures: Record<Identity, number> = { host: 0, guest: 0 };
  const activeSnapshotHolds: Record<Identity, SnapshotHold | null> = { host: null, guest: null };
  const nextCommandSnapshotHolds: Record<Identity, SnapshotHold | null> = { host: null, guest: null };
  let eventHeadSequence = gameplayContract.states[initialState].host.event_head_sequence;
  const discussionMessages = clone(
    gameplayContract.states[initialState].host.discussion_messages,
  );
  const presence = new Map<Identity, ScenePresence>([
    ["host", { x: 1455, y: 970, facing: "left", moving: false }],
    ["guest", { x: 945, y: 970, facing: "right", moving: false }],
  ]);
  const presenceBodies: Array<{ identity: Identity; body: PresencePayload }> = [];
  const appliedPresenceBodies: Array<{ identity: Identity; body: PresencePayload }> = [];
  let abortedPresenceRequests = 0;
  const commandBodies: Array<{ identity: Identity; type: string; payload: Record<string, unknown> }> = [];
  const reviewRequests: Identity[] = [];

  const snapshotFor = (identity: Identity) => {
    const snapshot = clone(gameplayContract.states[stateKey][identity]);
    snapshot.event_head_sequence = eventHeadSequence;
    snapshot.discussion_messages = clone(discussionMessages);
    if (!publicMaterialsVisible) snapshot.public_materials = [];
    if (!settlementVisible) snapshot.settlement = null;
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
      event_sequence: 0,
      result: null,
      error: { code, message, details: {} },
      replayed: false,
    });
  };

  const activateNextSnapshotHold = (identity: Identity) => {
    const hold = nextCommandSnapshotHolds[identity];
    if (!hold) return;
    nextCommandSnapshotHolds[identity] = null;
    activeSnapshotHolds[identity] = hold;
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
        snapshotRequests[identity] += 1;
        const hold = activeSnapshotHolds[identity];
        if (hold) {
          await hold.promise;
          if (activeSnapshotHolds[identity] === hold) activeSnapshotHolds[identity] = null;
        }
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
        const wasHeld = holdNextPresence;
        if (wasHeld) {
          holdNextPresence = false;
          await new Promise<void>((resolve) => {
            releaseHeldPresence = resolve;
          });
          releaseHeldPresence = null;
        }
        if (wasHeld && request.failure()) {
          abortedPresenceRequests += 1;
          return;
        }
        await route.fulfill({ status: 204, body: "" });
        presence.set(identity, { x: body.x, y: body.y, facing: body.facing, moving: body.moving });
        appliedPresenceBodies.push({ identity, body });
        return;
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
          if (
            current.status !== "active"
            || current.phase !== "discuss"
            || body.payload.stage_id !== current.stage_id
            || typeof body.payload.message_id !== "string"
            || typeof body.payload.text !== "string"
          ) {
            return rejectCommand(route, body.command_id, "PHASE_MISMATCH", "Wrong phase");
          }
          expect(body.payload.message_id).toMatch(/^[0-9a-f-]{36}$/i);
          if (messageFailures > 0) {
            messageFailures -= 1;
            return rejectCommand(route, body.command_id, "TEMPORARY_FAILURE", "Message send failed");
          }
          eventHeadSequence += 1;
          discussionMessages.push({
            sequence: eventHeadSequence,
            message_id: body.payload.message_id,
            stage_id: current.stage_id,
            member_id: members[identity].memberId,
            character_id: members[identity].characterId,
            text: body.payload.text,
          } satisfies GameplayDiscussionMessage);
          if (transition) stateKey = transition.to;
          activateNextSnapshotHold(identity);
          return json(route, {
            command_id: body.command_id,
            status: "accepted",
            revision: transition?.revision ?? current.revision,
            event_sequence: eventHeadSequence,
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
        const receiptEventSequence = transition.event_sequence === 0
          ? 0
          : eventHeadSequence + 1;
        if (receiptEventSequence > 0) eventHeadSequence = receiptEventSequence;
        activateNextSnapshotHold(identity);
        return json(route, {
          command_id: body.command_id,
          status: "accepted",
          revision: transition.revision,
          event_sequence: receiptEventSequence,
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
    hideSettlement() {
      settlementVisible = false;
    },
    setPresence(identity: Identity, pose: ScenePresence) {
      presence.set(identity, pose);
    },
    holdSnapshotsAfterNextCommand(identity: Identity) {
      let release: () => void = () => undefined;
      const promise = new Promise<void>((resolve) => {
        release = resolve;
      });
      nextCommandSnapshotHolds[identity] = { promise, release };
      return release;
    },
    setState(nextState: string) {
      stateKey = nextState;
    },
    holdNextPresence() {
      holdNextPresence = true;
    },
    releasePresence() {
      releaseHeldPresence?.();
    },
    commandBodies,
    presenceBodies,
    appliedPresenceBodies,
    getAbortedPresenceRequests: () => abortedPresenceRequests,
    reviewRequests,
    snapshotRequests,
  };
}

async function createPlayerPage(
  browser: Browser,
  api: ReturnType<typeof createGameplayApi>,
  identity: Identity,
  contextOptions: BrowserContextOptions = {},
) {
  const context = await browser.newContext(contextOptions);
  const { token, getSignupRequests } = await installAnonymousAuth(context, identity);
  const page = await context.newPage();
  const webSockets: string[] = [];
  page.on("websocket", (socket) => {
    if (!socket.url().includes("/_next/")) webSockets.push(socket.url());
  });
  await api.install(page, identity, token);
  return { context, page, webSockets, getSignupRequests };
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
    const initialMaterialTitle = hostSnapshot.public_materials[0].title;
    await expect(host.page.getByText(initialMaterialTitle)).toBeVisible();
    await host.page.evaluate((materialTitle) => {
      const observer = new MutationObserver(() => {
        const dialog = document.querySelector('[role="dialog"]');
        if (dialog?.textContent?.includes("公开档案") && !dialog.textContent.includes(materialTitle)) {
          document.documentElement.dataset.invalidMaterialPanelFrame = "true";
        }
      });
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }, initialMaterialTitle);

    api.hidePublicMaterials();
    await expect(host.page.getByRole("button", { name: "打开公开档案" })).toHaveCount(0, { timeout: 8_000 });
    await expect(host.page.getByRole("heading", { name: "公开档案" })).toHaveCount(0);
    await expect(host.page.getByRole("complementary", { name: "双人进度" })).toBeFocused();
    await expect(host.page.locator("html")).not.toHaveAttribute("data-invalid-material-panel-frame", "true");

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
    await host.page.getByRole("button", { name: "打开公开档案" }).focus();
    await expect(hintCloseButton).toBeFocused();
    await host.page.keyboard.press("Shift+Tab");
    await expect(hintDialog.getByRole("button", { name: "请求第 1 级提示" })).toBeFocused();
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

test("Sheet restores focus to a replacement trigger with the same logical identity", async ({ browser }) => {
  const api = createGameplayApi("investigation_discuss");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    const discussionEntry = host.page.getByRole("button", { name: "打开讨论" });
    await discussionEntry.focus();
    await host.page.keyboard.press("Enter");
    await expect(host.page.getByRole("dialog", { name: "双人公开讨论" })).toBeVisible();

    await host.page.evaluate(() => {
      const trigger = document.querySelector<HTMLElement>('[data-sheet-trigger="discussion"]');
      if (!trigger) throw new Error("discussion trigger missing");
      trigger.replaceWith(trigger.cloneNode(true));
    });
    await host.page.keyboard.press("Escape");
    await expect(host.page.getByRole("button", { name: "打开讨论" })).toBeFocused();
  } finally {
    await host.context.close();
  }
});

test("settlement radio group follows native Tab order including disabled fieldset descendants", async ({ browser }) => {
  const api = createGameplayApi("investigation_settle");
  const host = await createPlayerPage(browser, api, "host");
  const settlement = gameplayContract.states.investigation_settle.host.settlement!;

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "提交判断");
    await host.page.getByRole("button", { name: "打开判断" }).click();

    const dialog = host.page.getByRole("dialog", { name: "圆桌判断" });
    const closeButton = dialog.getByRole("button", { name: "关闭" });
    const radios = dialog.getByRole("radio");
    await expect(closeButton).toBeFocused();
    await host.page.keyboard.press("Tab");
    await expect(radios.first()).toBeFocused();
    await host.page.keyboard.press("Tab");
    await expect(closeButton).toBeFocused();

    await host.page.getByText(settlement.options[0].text, { exact: true }).click();
    await host.page.getByRole("button", { name: "确认选择" }).click();
    await expect(dialog.getByRole("button", { name: "已提交，等待同伴" })).toBeDisabled({ timeout: 8_000 });
    await expect(dialog.locator("fieldset")).toHaveAttribute("disabled", "");
    await expect(radios).toHaveCount(settlement.options.length);
    for (let index = 0; index < settlement.options.length; index += 1) {
      await expect(radios.nth(index)).toBeDisabled();
    }
    await closeButton.focus();
    await host.page.keyboard.press("Tab");
    await expect(closeButton).toBeFocused();
  } finally {
    await host.context.close();
  }
});

test("cached gameplay snapshot recovers after polling interruption", async ({ browser }) => {
  const api = createGameplayApi("investigation_discuss");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "公开讨论");

    api.failNextSnapshots("host", 20);
    const syncWarning = host.page.getByText("同步暂时中断，正在显示上次成功状态。");
    await expect(syncWarning).toBeVisible({ timeout: 15_000 });
    api.restoreSnapshots("host");
    await host.page.getByRole("button", { name: "重试同步" }).click();
    await expect(syncWarning).toHaveCount(0, { timeout: 8_000 });
    await expectScenePhase(host.page, "核对口供", "公开讨论");
  } finally {
    await host.context.close();
  }
});

test("discussion command failure preserves its draft and keyboard recovery keeps the Sheet open", async ({ browser }) => {
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
    await host.page.getByRole("button", { name: "打开讨论" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    const discussionDialog = host.page.getByRole("dialog", { name: "双人公开讨论" });
    const messageInput = discussionDialog.getByRole("textbox", { name: "讨论消息" });
    const sendMessageButton = discussionDialog.getByRole("button", { name: "发送讨论消息" });
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
    const commandError = discussionDialog.getByRole("alert").filter({ hasText: "Message send failed" });
    await expect(commandError).toBeVisible();
    const dialogCloseButton = discussionDialog.getByRole("button", { name: "关闭" });
    const syncButton = commandError.getByRole("button", { name: "同步" });
    await dialogCloseButton.focus();
    await host.page.keyboard.press("Tab");
    await expect(syncButton).toBeFocused();
    await host.page.keyboard.press("Enter");
    await expect(commandError).toHaveCount(0);
    await expect(discussionDialog).toBeVisible();
    await expect(discussionDialog).toBeFocused();
    await expect(messageInput).toHaveValue("门锁没有损坏。");

    await sendMessageButton.click();
    await expect(messageInput).toHaveValue("");
    await expect(guest.page.getByText("门锁没有损坏。")).toBeVisible({ timeout: 8_000 });
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});

test("accepted discussion message stays pending until the authoritative snapshot refreshes", async ({ browser }) => {
  const api = createGameplayApi("investigation_discuss");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await host.page.getByRole("button", { name: "打开讨论" }).click();
    const dialog = host.page.getByRole("dialog", { name: "双人公开讨论" });
    const messageInput = dialog.getByRole("textbox", { name: "讨论消息" });
    const sendButton = dialog.getByRole("button", { name: "发送讨论消息" });
    const releaseSnapshot = api.holdSnapshotsAfterNextCommand("host");

    await messageInput.fill("门锁没有损坏。");
    await sendButton.click();
    await expect.poll(
      () => api.commandBodies.filter(({ type }) => type === "discussion.send_message").length,
    ).toBe(1);
    await expect(sendButton).toBeDisabled();
    await expect(messageInput).toHaveValue("门锁没有损坏。");
    await host.page.waitForTimeout(500);
    expect(api.commandBodies.filter(({ type }) => type === "discussion.send_message")).toHaveLength(1);

    api.failNextSnapshots("host", 20);
    releaseSnapshot();
    const refreshError = dialog.getByRole("alert").filter({ hasText: "Temporary snapshot failure" });
    await expect(refreshError).toBeVisible({ timeout: 12_000 });
    await expect(sendButton).toBeDisabled();
    await expect(messageInput).toHaveValue("门锁没有损坏。");

    api.restoreSnapshots("host");
    await refreshError.getByRole("button", { name: "同步" }).click();
    await expect(refreshError).toHaveCount(0);
    await expect(messageInput).toHaveValue("");

    await messageInput.fill("照片时间与口供不一致。");
    await sendButton.click();
    await expect.poll(
      () => api.commandBodies.filter(({ type }) => type === "discussion.send_message").length,
    ).toBe(2);
    await expect(dialog.getByText("照片时间与口供不一致。")).toBeVisible();
  } finally {
    await host.context.close();
  }
});

test("completed players can reopen the public discussion transcript read-only", async ({ browser }) => {
  const api = createGameplayApi("message_completed");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expect(host.page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "打开讨论" }).click();
    const dialog = host.page.getByRole("dialog", { name: "双人公开讨论" });
    await expect(dialog.getByText("门锁没有损坏。")).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: "讨论消息" })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: /发送讨论消息|确认结束讨论|撤销结束确认/ })).toHaveCount(0);
  } finally {
    await host.context.close();
  }
});

test("a reveal stage without settlement still exposes the fixed advance action", async ({ browser }) => {
  const api = createGameplayApi("investigation_reveal");
  api.hideSettlement();
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "查看结果");
    await host.page.getByRole("button", { name: "打开结论" }).click();
    const dialog = host.page.getByRole("dialog", { name: "阶段结论" });
    await expect(dialog.getByRole("button", { name: "进入下一阶段" })).toBeVisible();
    await dialog.getByRole("button", { name: "进入下一阶段" }).click();
    await expectScenePhase(host.page, "共同终判", "阅读角色信息");
  } finally {
    await host.context.close();
  }
});

test("completed review retries without replaying the game journey", async ({ browser }) => {
  const api = createGameplayApi("completed");
  api.failNextReviews("host");
  const host = await createPlayerPage(browser, api, "host");
  const hostReview = gameplayContract.reviews.host;

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expect(host.page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({ timeout: 8_000 });
    await host.page.getByRole("button", { name: "打开复盘" }).click();
    await expect(host.page.getByText("Temporary review failure", { exact: true })).toBeVisible({ timeout: 12_000 });
    await host.page.getByRole("button", { name: "重新加载复盘" }).click();
    await expect(host.page.getByRole("heading", { name: hostReview.ending.name })).toBeVisible({ timeout: 8_000 });
    await expect(host.page.getByText(hostReview.ending.outcome_text)).toBeVisible();
  } finally {
    await host.context.close();
  }
});

test("active rooms retain recovery polling and presence traffic", async ({ browser }) => {
  const api = createGameplayApi("investigation_discuss");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    const snapshotCount = api.snapshotRequests.host;
    await expect.poll(() => api.snapshotRequests.host, { timeout: 4_000 }).toBeGreaterThan(snapshotCount);
    await expect.poll(
      () => api.presenceBodies.filter(({ identity }) => identity === "host").length,
      { timeout: 4_000 },
    ).toBeGreaterThan(0);
  } finally {
    await host.context.close();
  }
});

test("completion cancels gameplay traffic and navigation does not revive it", async ({ browser }) => {
  test.setTimeout(60_000);
  const api = createGameplayApi("investigation_discuss");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await expect.poll(
      () => api.appliedPresenceBodies.filter(({ identity }) => identity === "host").length,
    ).toBeGreaterThan(0);
    await host.page.waitForTimeout(750);
    const presenceCount = api.presenceBodies.filter(
      ({ identity }) => identity === "host",
    ).length;
    const appliedPresenceCount = api.appliedPresenceBodies.filter(
      ({ identity }) => identity === "host",
    ).length;
    api.holdNextPresence();

    await host.page.keyboard.down("KeyD");
    await expect.poll(
      () => api.presenceBodies.filter(({ identity }) => identity === "host").length,
    ).toBe(presenceCount + 1);
    await host.page.waitForTimeout(650);
    await host.page.keyboard.up("KeyD");
    api.setState("completed");
    await expect(
      host.page.getByText("当前阶段 · 游戏完成", { exact: true }),
    ).toBeVisible({ timeout: 8_000 });
    const completedSnapshotCount = api.snapshotRequests.host;

    api.releasePresence();
    await expect.poll(api.getAbortedPresenceRequests).toBe(1);
    await host.page.waitForTimeout(5_500);
    expect(api.snapshotRequests.host).toBe(completedSnapshotCount);
    expect(
      api.presenceBodies.filter(({ identity }) => identity === "host"),
    ).toHaveLength(presenceCount + 1);
    expect(
      api.appliedPresenceBodies.filter(({ identity }) => identity === "host"),
    ).toHaveLength(appliedPresenceCount);

    await host.page.getByRole("button", { name: "打开复盘" }).click();
    const endingName = gameplayContract.reviews.host.ending.name;
    await expect(host.page.getByRole("heading", { name: endingName })).toBeVisible({ timeout: 8_000 });
    expect(api.reviewRequests).toEqual(["host"]);
    const backgroundPage = await host.context.newPage();
    await backgroundPage.goto("about:blank");
    await backgroundPage.bringToFront();
    await host.page.bringToFront();
    await host.context.setOffline(true);
    await host.context.setOffline(false);
    await host.page.waitForTimeout(1_500);
    expect(api.snapshotRequests.host).toBe(completedSnapshotCount);
    expect(api.reviewRequests).toEqual(["host"]);

    await host.page.goto(`/play/${sessionId}/review`);
    await expect(host.page.getByRole("heading", { name: endingName })).toBeVisible({ timeout: 8_000 });
    expect(api.reviewRequests).toEqual(["host", "host"]);
    await host.page.waitForTimeout(5_500);
    expect(api.snapshotRequests.host).toBe(completedSnapshotCount);
    expect(
      api.presenceBodies.filter(({ identity }) => identity === "host"),
    ).toHaveLength(presenceCount + 1);
  } finally {
    api.releasePresence();
    await host.context.close();
  }
});

test("direct completed review cold-loads and refreshes without gameplay traffic", async ({ browser }) => {
  test.setTimeout(45_000);
  const api = createGameplayApi("completed");
  const host = await createPlayerPage(browser, api, "host");

  try {
    await host.page.goto(`/play/${sessionId}/review`);
    const endingName = gameplayContract.reviews.host.ending.name;
    await expect(host.page.getByRole("heading", { name: endingName })).toBeVisible({ timeout: 8_000 });
    expect(host.getSignupRequests()).toBe(1);
    expect(api.reviewRequests).toEqual(["host"]);
    expect(api.snapshotRequests.host).toBe(0);
    expect(api.presenceBodies.filter(({ identity }) => identity === "host")).toHaveLength(0);

    const backgroundPage = await host.context.newPage();
    await backgroundPage.goto("about:blank");
    await backgroundPage.bringToFront();
    await host.page.bringToFront();
    await host.context.setOffline(true);
    await host.context.setOffline(false);
    await host.page.waitForTimeout(5_500);
    expect(api.reviewRequests).toEqual(["host"]);
    expect(api.snapshotRequests.host).toBe(0);
    expect(api.presenceBodies.filter(({ identity }) => identity === "host")).toHaveLength(0);

    await host.page.reload();
    await expect(host.page.getByRole("heading", { name: endingName })).toBeVisible({ timeout: 8_000 });
    expect(host.getSignupRequests()).toBe(1);
    expect(api.reviewRequests).toEqual(["host", "host"]);
    await host.page.getByRole("button", { name: "刷新复盘" }).click();
    await expect.poll(() => api.reviewRequests.length).toBe(3);
    expect(api.snapshotRequests.host).toBe(0);
    expect(api.presenceBodies.filter(({ identity }) => identity === "host")).toHaveLength(0);
  } finally {
    await host.context.close();
  }
});


test("scene review hotspot opens the same completed surface as the fixed entry", async ({ context, page }) => {
  const api = createGameplayApi("completed");
  api.setPresence("host", { x: 1500, y: 1150, facing: "left", moving: false });
  const { token } = await installAnonymousAuth(context, "host");
  await api.install(page, "host", token);
  const hostReview = gameplayContract.reviews.host;

  await page.goto(`/play/${sessionId}/lobby`);
  await expect(page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({ timeout: 8_000 });

  await page.getByRole("button", { name: "打开复盘" }).click();
  const reviewDialog = page.getByRole("dialog", { name: "案件复盘" });
  await expect(reviewDialog.getByRole("heading", { name: hostReview.ending.name })).toBeVisible();
  await expect(reviewDialog.getByText(hostReview.ending.outcome_text)).toBeVisible();
  await reviewDialog.getByRole("button", { name: "关闭" }).click();
  await expect(reviewDialog).toHaveCount(0);

  const commandCount = api.commandBodies.length;
  const reviewHotspot = page.locator('[data-hotspot-id="multiplayer-review"]');
  await expect(reviewHotspot).toBeEnabled();
  await reviewHotspot.click();
  await expect(reviewDialog.getByRole("heading", { name: hostReview.ending.name })).toBeVisible();
  await expect(reviewDialog.getByText(hostReview.ending.outcome_text)).toBeVisible();
  expect(api.commandBodies).toHaveLength(commandCount);
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

    await host.page.getByRole("button", { name: "打开讨论" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    const messageInput = host.page.getByRole("textbox", { name: "讨论消息" });
    await messageInput.fill("门锁没有损坏。");
    await host.page.getByRole("button", { name: "发送讨论消息" }).click();
    await expect(messageInput).toHaveValue("");
    await expect(guest.page.getByText("门锁没有损坏。")).toBeVisible({ timeout: 8_000 });
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
    await expectScenePhase(guest.page, "共同终判", "阅读角色信息");
    const retainedMaterialTitles = gameplayContract.states.investigation_read.host.public_materials
      .map((material) => material.title);
    const cumulativeMaterialTitles = gameplayContract.states.message_final_read.host.public_materials
      .map((material) => material.title);
    expect(cumulativeMaterialTitles).toEqual(expect.arrayContaining(retainedMaterialTitles));
    await host.page.getByRole("button", { name: "打开公开档案" }).click();
    for (const title of cumulativeMaterialTitles) {
      await expect(host.page.getByText(title)).toBeVisible();
    }
    await host.page.getByRole("button", { name: "关闭" }).click();

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
    await expect(host.page.getByRole("dialog", { name: "圆桌判断" })).toHaveCount(0);
    await expect(guest.page.getByRole("dialog", { name: "圆桌判断" })).toHaveCount(0);
    await host.page.getByRole("dialog", { name: "阶段结论" }).getByRole("button", { name: "关闭" }).click();
    await guest.page.getByRole("dialog", { name: "阶段结论" }).getByRole("button", { name: "关闭" }).click();

    await host.page.getByRole("button", { name: "打开复盘" }).click();
    await expect(host.page.getByRole("heading", { name: gameplayContract.reviews.host.ending.name })).toBeVisible({ timeout: 8_000 });
    await guest.page.getByRole("button", { name: "打开复盘" }).click();
    await expect(guest.page.getByRole("heading", { name: gameplayContract.reviews.guest.ending.name })).toBeVisible({ timeout: 8_000 });
    expect(host.webSockets).toEqual([]);
    expect(guest.webSockets).toEqual([]);
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});

test("@mobile 390x844 touch controls and Sheet actions remain operable", async ({ browser }) => {
  test.setTimeout(60_000);
  const mobileOptions: BrowserContextOptions = {
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  };
  const api = createGameplayApi();
  const settlementApi = createGameplayApi("investigation_settle");
  const reviewApi = createGameplayApi("completed");
  const host = await createPlayerPage(browser, api, "host", mobileOptions);
  const guest = await createPlayerPage(browser, api, "guest");
  const settlementHost = await createPlayerPage(browser, settlementApi, "host", mobileOptions);
  const reviewHost = await createPlayerPage(browser, reviewApi, "host", mobileOptions);

  try {
    await Promise.all([
      host.page.goto(`/play/${sessionId}/lobby`),
      guest.page.goto(`/play/${sessionId}/lobby`),
    ]);
    await expectScenePhase(host.page, "核对口供", "阅读角色信息");
    await expectScenePhase(guest.page, "核对口供", "阅读角色信息");
    expect(await host.page.evaluate(() => navigator.maxTouchPoints)).toBeGreaterThan(0);

    const scene = host.page.locator(".mansion-demo");
    const initialX = Number(await scene.getAttribute("data-player-x"));
    const right = host.page.getByRole("button", { name: "向右" });
    await right.dispatchEvent("pointerdown", { pointerId: 1, pointerType: "touch", isPrimary: true });
    await host.page.waitForTimeout(500);
    await right.dispatchEvent("pointerup", { pointerId: 1, pointerType: "touch", isPrimary: true });
    await expect.poll(async () => Number(await scene.getAttribute("data-player-x"))).toBeGreaterThan(initialX);

    const archiveEntry = host.page.getByRole("button", { name: "打开公开档案" });
    const entryBox = await archiveEntry.boundingBox();
    expect(entryBox).not.toBeNull();
    expect(entryBox!.x).toBeGreaterThanOrEqual(0);
    expect(entryBox!.x + entryBox!.width).toBeLessThanOrEqual(390);
    expect(entryBox!.y + entryBox!.height).toBeLessThanOrEqual(844);
    await archiveEntry.tap();
    const archiveDialog = host.page.getByRole("dialog", { name: "公开档案" });
    await expect(archiveDialog).toBeInViewport();
    await expect(archiveDialog.getByText(gameplayContract.states.investigation_read.host.public_materials[0].title)).toBeVisible();
    const archiveClose = archiveDialog.getByRole("button", { name: "关闭" });
    await expect.poll(async () => {
      const closeBox = await archiveClose.boundingBox();
      return closeBox ? closeBox.y + closeBox.height : Number.POSITIVE_INFINITY;
    }).toBeLessThanOrEqual(844);
    await archiveClose.tap();

    await host.page.getByRole("button", { name: "角色章" }).tap();
    await host.page.getByRole("button", { name: "我已读完" }).tap();
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    await guest.page.getByRole("button", { name: "角色章" }).click();
    await guest.page.getByRole("button", { name: "我已读完" }).click();
    await expectScenePhase(host.page, "核对口供", "公开讨论");
    await host.page.getByRole("button", { name: "关闭" }).tap();
    await guest.page.getByRole("button", { name: "关闭" }).click();

    await host.page.getByRole("button", { name: "打开讨论" }).tap();
    const discussionDialog = host.page.getByRole("dialog", { name: "双人公开讨论" });
    const messageInput = discussionDialog.getByRole("textbox", { name: "讨论消息" });
    await messageInput.fill("门锁没有损坏。");
    await discussionDialog.getByRole("button", { name: "发送讨论消息" }).tap();
    await expect(messageInput).toHaveValue("");
    await discussionDialog.getByRole("button", { name: "关闭" }).tap();

    await host.page.getByRole("button", { name: "打开协作提示" }).tap();
    const hintDialog = host.page.getByRole("dialog", { name: "协作提示" });
    await expect(hintDialog).toBeInViewport();
    await hintDialog.getByRole("button", { name: "请求第 1 级提示" }).tap();
    await expect(hintDialog.getByRole("button", { name: "已确认，等待同伴" })).toBeDisabled();

    await settlementHost.page.goto(`/play/${sessionId}/lobby`);
    await expectScenePhase(settlementHost.page, "核对口供", "提交判断");
    await settlementHost.page.getByRole("button", { name: "打开判断" }).tap();
    const settlementDialog = settlementHost.page.getByRole("dialog", { name: "圆桌判断" });
    const settlement = gameplayContract.states.investigation_settle.host.settlement!;
    await settlementDialog.getByText(settlement.options[0].text, { exact: true }).tap();
    await settlementDialog.getByRole("button", { name: "确认选择" }).tap();
    await expect(settlementDialog.getByRole("button", { name: "已提交，等待同伴" })).toBeDisabled();

    await reviewHost.page.goto(`/play/${sessionId}/lobby`);
    await expect(reviewHost.page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({ timeout: 8_000 });
    await reviewHost.page.getByRole("button", { name: "打开复盘" }).tap();
    const reviewDialog = reviewHost.page.getByRole("dialog", { name: "案件复盘" });
    await expect(reviewDialog).toBeInViewport();
    await expect(reviewDialog.getByRole("heading", { name: gameplayContract.reviews.host.ending.name })).toBeVisible();
  } finally {
    await Promise.all([
      host.context.close(),
      guest.context.close(),
      settlementHost.context.close(),
      reviewHost.context.close(),
    ]);
  }
});
