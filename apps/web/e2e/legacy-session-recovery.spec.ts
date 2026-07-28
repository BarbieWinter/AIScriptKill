import { expect, test, type Page, type Route } from "@playwright/test";

const sessionId = "11111111-1111-4111-8111-111111111111";

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

function session(revision: number, eventHead: number) {
  return {
    session_id: sessionId,
    script_id: "snow-village",
    status: "in_progress",
    current_stage: "back_door_judgement",
    stage_name: "后门判断",
    player_character_id: "zhuosiyuan",
    available_actions: ["talk_to_npc", "examine_scene", "request_advance"],
    available_characters: ["wangdada"],
    unlocked_clues_count: 0,
    total_clues_in_round: 1,
    discovered_evidences: [],
    viewed_evidences: [],
    current_scene: "back-alley",
    pending_media: [],
    revision,
    event_head_sequence: eventHead,
  };
}

function resources(pathname: string, revision: number, eventHead: number) {
  if (pathname === `/api/v1/sessions/${sessionId}`) return session(revision, eventHead);
  if (pathname.endsWith("/characters")) {
    return {
      characters: [{
        id: "wangdada",
        name: "王大达",
        portrait_url: "",
        current_mood: "calm",
        mood_description: "",
        dialogue_available: true,
      }],
    };
  }
  if (pathname.endsWith("/clues")) return { clues: [] };
  if (pathname.endsWith("/evidences")) return { evidences: [] };
  if (pathname.endsWith("/chat-history")) return { messages: [] };
  if (pathname.endsWith("/cards")) return { cards: [] };
  if (pathname.endsWith("/presentation")) {
    return {
      stage: {
        id: "back_door_judgement",
        name: "后门判断",
        available_actions: ["talk_to_npc", "examine_scene", "request_advance"],
        available_characters: ["wangdada"],
      },
      scene: { id: "back-alley", name: "后门小巷", hotspots: [] },
      judgement: null,
    };
  }
  return null;
}

async function installBaseApi(page: Page) {
  let revision = 0;
  let eventHead = 0;
  const commandBodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const value = resources(pathname, revision, eventHead);
    if (value !== null && request.method() === "GET") return json(route, value);

    if (pathname.endsWith("/events") && request.method() === "GET") {
      const after = Number(url.searchParams.get("after_sequence") ?? 0);
      const events = after < eventHead
        ? [{
            sequence: eventHead,
            revision,
            command_id: String(commandBodies.at(-1)?.command_id),
            event_type: "command_succeeded",
            event_version: 1,
            payload: {},
            state_sha256: null,
          }]
        : [];
      return json(route, {
        revision,
        event_head_sequence: eventHead,
        snapshot: session(revision, eventHead),
        events,
        next_after_sequence: events.at(-1)?.sequence ?? after,
        has_more: false,
        reset_required: false,
      });
    }

    if (pathname.endsWith("/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      commandBodies.push(body);
      revision += 1;
      eventHead += 1;
      return json(route, {
        command_id: body.command_id,
        status: "succeeded",
        revision,
        event_sequence_from: eventHead,
        event_sequence_to: eventHead,
        result: {
          type: "npc_response",
          character_id: "wangdada",
          text: "我没有看清。",
          emotion: "calm",
          state_changes: {},
          triggered_events: [],
          media_triggers: [],
        },
        error_code: null,
        error_details: {},
      });
    }

    return apiError(route, 404, "NOT_FOUND", pathname);
  });

  return { commandBodies };
}

async function openChat(page: Page) {
  await page.getByTestId("chat-open").click();
  await expect(page.getByTestId("chat-input")).toBeVisible();
}

function succeededCommand(body: Record<string, unknown>, revision: number, eventHead: number) {
  return {
    command_id: body.command_id,
    status: "succeeded",
    revision,
    event_sequence_from: eventHead,
    event_sequence_to: eventHead,
    result: {
      type: "npc_response",
      character_id: "wangdada",
      text: "我没有看清。",
      emotion: "calm",
      state_changes: {},
      triggered_events: [],
      media_triggers: [],
    },
    error_code: null,
    error_details: {},
  };
}

function eventPage(
  revision: number,
  eventHead: number,
  after: number,
  commandId: unknown,
) {
  const events = after < eventHead
    ? [{
        sequence: eventHead,
        revision,
        command_id: String(commandId),
        event_type: "command_succeeded",
        event_version: 1,
        payload: {},
        state_sha256: null,
      }]
    : [];
  return {
    revision,
    event_head_sequence: eventHead,
    snapshot: session(revision, eventHead),
    events,
    next_after_sequence: events.at(-1)?.sequence ?? after,
    has_more: false,
    reset_required: false,
  };
}

test("clue detail covers the viewport and restores its trigger focus", async ({ page }) => {
  await installBaseApi(page);
  await page.route(`**/api/v1/sessions/${sessionId}/clues`, async (route) => {
    await json(route, {
      clues: [{
        id: "door-lock-photo",
        name: "门锁照片",
        image_url: "",
        description: "门锁没有损坏。",
        is_key: true,
        importance: 3,
        status: "unlocked",
      }],
    });
  });
  await page.goto(`/play/snow-village/${sessionId}`);

  await page.getByRole("button", { name: /线索板/ }).click();
  const clueBoard = page.getByRole("dialog", { name: "线索板" });
  const clueTrigger = page.getByRole("button", { name: /门锁照片/ });
  await clueTrigger.click();
  const detail = page.getByRole("dialog", { name: "线索详情：门锁照片" });
  await expect(detail).toBeVisible();
  const detailBox = await detail.boundingBox();
  const viewport = page.viewportSize();
  expect(detailBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(detailBox).toMatchObject({ x: 0, y: 0 });
  expect(detailBox?.width).toBe(viewport?.width);
  expect(detailBox?.height).toBe(viewport?.height);

  await detail.click({ position: { x: 4, y: 4 } });
  await expect(detail).toHaveCount(0);
  await expect(clueBoard).toBeVisible();
  await expect(clueTrigger).toBeFocused();

  await clueTrigger.click();
  await page.keyboard.press("Escape");
  await expect(detail).toHaveCount(0);
  await expect(clueTrigger).toBeFocused();
});

test("live action sends one durable command and advances the replay cursor", async ({ page }) => {
  const api = await installBaseApi(page);
  await page.goto(`/play/snow-village/${sessionId}`);
  await openChat(page);

  await page.getByTestId("chat-input").fill("你看见了谁？");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("recovery-status")).toHaveCount(0);

  expect(api.commandBodies).toHaveLength(1);
  expect(api.commandBodies[0].expected_revision).toBe(0);
  expect(api.commandBodies[0].command_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  );
});

test("lost POST response resolves from the receipt without duplicate mutation", async ({ page }) => {
  let revision = 0;
  let eventHead = 0;
  let receiptReads = 0;
  const bodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const value = resources(pathname, revision, eventHead);
    if (value !== null && request.method() === "GET") return json(route, value);
    if (pathname.endsWith("/events")) {
      return json(route, eventPage(
        revision,
        eventHead,
        Number(url.searchParams.get("after_sequence") ?? 0),
        bodies.at(-1)?.command_id,
      ));
    }
    if (pathname.endsWith("/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      revision = 1;
      eventHead = 1;
      return route.abort("connectionreset");
    }
    if (pathname.includes("/commands/") && request.method() === "GET") {
      receiptReads += 1;
      return json(route, succeededCommand(bodies[0], revision, eventHead));
    }
    return apiError(route, 404, "NOT_FOUND", pathname);
  });

  await page.goto(`/play/snow-village/${sessionId}`);
  await openChat(page);
  await page.getByTestId("chat-input").fill("响应丢失");
  await page.getByTestId("chat-send").click();
  await expect.poll(() => receiptReads).toBeGreaterThan(0);
  await expect(page.getByTestId("chat-input")).toHaveValue("");
  expect(bodies).toHaveLength(1);
});

test("missing receipt replays one byte-equivalent command envelope", async ({ page }) => {
  let revision = 0;
  let eventHead = 0;
  let receiptReads = 0;
  const bodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const value = resources(pathname, revision, eventHead);
    if (value !== null && request.method() === "GET") return json(route, value);
    if (pathname.endsWith("/events")) {
      return json(route, eventPage(
        revision,
        eventHead,
        Number(url.searchParams.get("after_sequence") ?? 0),
        bodies.at(-1)?.command_id,
      ));
    }
    if (pathname.endsWith("/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      if (bodies.length === 1) return route.abort("connectionreset");
      revision = 1;
      eventHead = 1;
      return json(route, succeededCommand(body, revision, eventHead));
    }
    if (pathname.includes("/commands/") && request.method() === "GET") {
      receiptReads += 1;
      return apiError(route, 404, "COMMAND_NOT_FOUND", "receipt missing");
    }
    return apiError(route, 404, "NOT_FOUND", pathname);
  });

  await page.goto(`/play/snow-village/${sessionId}`);
  await openChat(page);
  await page.getByTestId("chat-input").fill("只重发一次");
  await page.getByTestId("chat-send").click();
  await expect.poll(() => bodies.length).toBe(2);
  expect(receiptReads).toBe(1);
  expect(bodies[1]).toEqual(bodies[0]);
});

test("processing budget becomes uncertain and manual recovery keeps the UUID", async ({ page }) => {
  let receiptReads = 0;
  const bodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const value = resources(pathname, 0, 0);
    if (value !== null && request.method() === "GET") return json(route, value);
    if (pathname.endsWith("/events")) {
      return json(route, eventPage(0, 0, Number(url.searchParams.get("after_sequence") ?? 0), null));
    }
    if (pathname.endsWith("/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      return apiError(route, 409, "COMMAND_IN_PROGRESS", "processing");
    }
    if (pathname.includes("/commands/") && request.method() === "GET") {
      receiptReads += 1;
      return json(route, {
        command_id: bodies[0].command_id,
        status: "processing",
        revision: 0,
        event_sequence_from: null,
        event_sequence_to: null,
        result: null,
        error_code: null,
        error_details: {},
      });
    }
    return apiError(route, 404, "NOT_FOUND", pathname);
  });

  await page.goto(`/play/snow-village/${sessionId}`);
  await openChat(page);
  await page.getByTestId("chat-input").fill("还在处理");
  await page.getByTestId("chat-send").click();
  await expect(page.getByTestId("recovery-status")).toContainText("待确认", { timeout: 10_000 });
  const readsAfterBudget = receiptReads;
  await page.waitForTimeout(250);
  expect(receiptReads).toBe(readsAfterBudget);
  expect(bodies).toHaveLength(1);

  await page.getByTestId("recovery-retry").click();
  await expect.poll(() => receiptReads).toBeGreaterThan(readsAfterBudget);
  expect(bodies[0].command_id).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  );
  expect(bodies).toHaveLength(1);
});

test("event gap performs one cursor-zero reset before applying the snapshot", async ({ page }) => {
  let revision = 1;
  let eventHead = 1;
  let gapServed = false;
  const eventCursors: number[] = [];
  const bodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const value = resources(pathname, revision, eventHead);
    if (value !== null && request.method() === "GET") return json(route, value);
    if (pathname.endsWith("/actions") && request.method() === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      revision = 3;
      eventHead = 3;
      return json(route, succeededCommand(body, revision, eventHead));
    }
    if (pathname.endsWith("/events")) {
      const after = Number(url.searchParams.get("after_sequence") ?? 0);
      eventCursors.push(after);
      if (!gapServed) {
        gapServed = true;
        return json(route, {
          revision,
          event_head_sequence: eventHead,
          snapshot: session(revision, eventHead),
          events: [{
            sequence: 3,
            revision,
            command_id: String(bodies[0].command_id),
            event_type: "command_succeeded",
            event_version: 1,
            payload: {},
            state_sha256: null,
          }],
          next_after_sequence: 3,
          has_more: false,
          reset_required: false,
        });
      }
      return json(route, {
        revision,
        event_head_sequence: eventHead,
        snapshot: session(revision, eventHead),
        events: [1, 2, 3].map((sequence) => ({
          sequence,
          revision: sequence,
          command_id: String(bodies[0].command_id),
          event_type: "command_succeeded",
          event_version: 1,
          payload: {},
          state_sha256: null,
        })),
        next_after_sequence: 3,
        has_more: false,
        reset_required: false,
      });
    }
    return apiError(route, 404, "NOT_FOUND", pathname);
  });

  await page.goto(`/play/snow-village/${sessionId}`);
  await openChat(page);
  await page.getByTestId("chat-input").fill("检测事件缺口");
  await page.getByTestId("chat-send").click();
  await expect.poll(() => eventCursors.length).toBe(2);
  await expect(page.getByTestId("chat-input")).toHaveValue("");
  expect(eventCursors).toEqual([1, 0]);
  expect(bodies).toHaveLength(1);
});

test("revision conflict resyncs without replaying the stale intent", async ({ page }) => {
  let revision = 0;
  let eventHead = 0;
  const bodies: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const value = resources(pathname, revision, eventHead);
    if (value !== null && request.method() === "GET") return json(route, value);
    if (pathname.endsWith("/events")) {
      return json(route, {
        revision,
        event_head_sequence: eventHead,
        snapshot: session(revision, eventHead),
        events: [],
        next_after_sequence: Number(url.searchParams.get("after_sequence") ?? 0),
        has_more: false,
        reset_required: false,
      });
    }
    if (pathname.endsWith("/actions")) {
      const body = request.postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      if (bodies.length === 1) {
        revision = 2;
        eventHead = 0;
        return apiError(route, 409, "SESSION_REVISION_CONFLICT", "revision changed");
      }
      revision += 1;
      eventHead += 1;
      return json(route, {
        command_id: body.command_id,
        status: "succeeded",
        revision,
        event_sequence_from: eventHead,
        event_sequence_to: eventHead,
        result: {
          type: "npc_response",
          character_id: "wangdada",
          text: "我没有看清。",
          emotion: "calm",
          state_changes: {},
          triggered_events: [],
          media_triggers: [],
        },
        error_code: null,
        error_details: {},
      });
    }
    return apiError(route, 404, "NOT_FOUND", pathname);
  });

  await page.goto(`/play/snow-village/${sessionId}`);
  await openChat(page);
  await page.getByTestId("chat-input").fill("第一次");
  await page.getByTestId("chat-send").click();
  await expect.poll(() => bodies.length).toBe(1);

  await page.getByTestId("chat-input").fill("第二次");
  await page.getByTestId("chat-send").click();
  await expect.poll(() => bodies.length).toBe(2);
  expect(bodies[1].expected_revision).toBe(2);
  expect(bodies[1].command_id).not.toBe(bodies[0].command_id);
});
