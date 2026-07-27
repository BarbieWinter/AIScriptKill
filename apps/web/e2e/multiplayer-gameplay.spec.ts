import { expect, test, type Browser, type BrowserContext, type Page, type Route } from "@playwright/test";

type Identity = "host" | "guest";
type Phase = "read" | "discuss" | "settle" | "reveal";

type ScenePresence = {
  x: number;
  y: number;
  facing: "left" | "right";
  moving: boolean;
};

type PresencePayload = ScenePresence & Record<string, unknown>;

const sessionId = "22222222-2222-4222-8222-222222222222";
const members = {
  host: { memberId: "member-host", characterId: "investigator", characterName: "调查员" },
  guest: { memberId: "member-guest", characterId: "insider", characterName: "知情人" },
} as const;

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
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

function createGameplayApi() {
  let status: "active" | "completed" = "active";
  let stageId: "investigation" | "final-judgment" = "investigation";
  let phase: Phase = "read";
  let revision = 5;
  let eventSequence = 5;
  let endingId: string | null = null;
  let sharedOptionId: string | null = null;
  let publicMaterialsVisible = true;
  let messageFailures = 0;
  const snapshotFailures: Record<Identity, number> = { host: 0, guest: 0 };
  const reviewFailures: Record<Identity, number> = { host: 0, guest: 0 };
  const read = new Set<Identity>();
  const readMembers = new Set<string>();
  const closed = new Set<Identity>();
  const votes = new Map<Identity, string>();
  const sharedConfirmations = new Set<Identity>();
  const messages: Array<{
    sequence: number;
    message_id: string;
    stage_id: string;
    member_id: string;
    character_id: string;
    text: string;
  }> = [];
  const presence = new Map<Identity, ScenePresence>([
    ["host", { x: 1455, y: 970, facing: "left", moving: false }],
    ["guest", { x: 945, y: 970, facing: "right", moving: false }],
  ]);
  const presenceBodies: Array<{ identity: Identity; body: PresencePayload }> = [];

  const settlement = (identity: Identity) => {
    if (phase !== "settle" && phase !== "reveal") return null;
    if (stageId === "investigation") {
      return {
        settlement_id: "investigation-vote",
        mode: "secret_vote",
        question: "二十点二十分的金属声最可能来自哪种情况？",
        options: [
          { id: "investigator-account", text: "有人在二十点二十分强行进入值班室" },
          { id: "insider-account", text: "有人早已在室内，金属声来自钥匙掉落" },
        ],
        submitted_member_ids: [...votes.keys()].map((item) => members[item].memberId),
        own_option_id: votes.get(identity) ?? null,
        shared_option_id: null,
        outcome_id: phase === "reveal" ? "split-vote" : null,
        revealed: phase === "reveal",
        reveal: "named_ballots",
        revealed_ballots: phase === "reveal"
          ? [...votes].map(([item, optionId]) => ({ member_id: members[item].memberId, option_id: optionId }))
          : [],
        revealed_option_counts: [],
      };
    }
    return {
      settlement_id: "final-judgment",
      mode: "final_judgment",
      question: "两人共同认可的案件判断是什么？",
      options: [
        { id: "records-insufficient", text: "认定知情人在二十点二十分强行进入，并故意损毁值班记录" },
        { id: "timeline-conflict", text: "认定知情人违规进入并隐瞒，但没有证据证明其破门或损毁记录" },
      ],
      submitted_member_ids: [...sharedConfirmations].map((item) => members[item].memberId),
      own_option_id: null,
      shared_option_id: sharedOptionId,
      outcome_id: status === "completed" ? "conflicting-accounts" : null,
      revealed: status === "completed",
      reveal: "outcome_only",
      revealed_ballots: [],
      revealed_option_counts: [],
    };
  };

  const snapshotFor = (identity: Identity) => {
    const player = members[identity];
    const chapters = stageId === "investigation"
      ? [{
          id: `${player.characterId}-investigation`,
          title: `${player.characterName}·核对口供`,
          content: identity === "host" ? "调查员私有线索：照片时间可疑。" : "知情人私有线索：门锁一直完好。",
        }]
      : [
          {
            id: `${player.characterId}-investigation`,
            title: `${player.characterName}·核对口供`,
            content: identity === "host" ? "调查员私有线索：照片时间可疑。" : "知情人私有线索：门锁一直完好。",
          },
          {
            id: `${player.characterId}-final-judgment`,
            title: `${player.characterName}·共同终判`,
            content: identity === "host" ? "调查员终判信息。" : "知情人终判信息。",
          },
        ];
    return {
      snapshot_version: 1,
      session_id: sessionId,
      mode: "multiplayer_v1",
      status,
      revision,
      event_head_sequence: eventSequence,
      package: { script_id: "mp1-two-player", title: "双人测试剧本", version: "1.0.0" },
      self_member_id: player.memberId,
      stage_id: stageId,
      stage_name: stageId === "investigation" ? "核对口供" : "共同终判",
      phase,
      suggested_discussion_minutes: stageId === "investigation" ? 12 : 8,
      players: Object.entries(members).map(([playerIdentity, item]) => {
        const pose = presence.get(playerIdentity as Identity);
        return {
          member_id: item.memberId,
          character_id: item.characterId,
          character_name: item.characterName,
          scene_x: pose?.x ?? null,
          scene_y: pose?.y ?? null,
          scene_facing: pose?.facing ?? null,
          scene_moving: pose?.moving ?? false,
          scene_online: pose !== undefined,
        };
      }),
      read_member_ids: [...readMembers],
      discussion_close_member_ids: [...closed].map((item) => members[item].memberId),
      chapters,
      public_materials: publicMaterialsVisible && stageId === "investigation"
        ? [{ id: "arrival-photo", kind: "clue", title: "抵达照片", text: "照片记录了抵达时刻。", media_type: null, url: null }]
        : publicMaterialsVisible && status === "completed"
          ? [{ id: "case-reconstruction", kind: "clue", title: "核验后的时间线", text: "知情人早已在室内，金属声来自钥匙落地。", media_type: null, url: null }]
          : [],
      discussion_messages: messages,
      settlement: settlement(identity),
      hints: [],
      can_advance: stageId === "investigation" && phase === "reveal",
      ending_id: endingId,
    };
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
        return json(route, status === "active" ? { session_id: sessionId, status: "active", mode: "multiplayer_v1" } : null);
      }
      if (pathname === `/api/v1/sessions/${sessionId}/review` && method === "GET") {
        if (reviewFailures[identity] > 0) {
          reviewFailures[identity] -= 1;
          return json(route, { error: { code: "TEMPORARY_FAILURE", message: "Temporary review failure", details: {} } }, 500);
        }
        return json(route, {
          review_version: 1,
          session_id: sessionId,
          member_id: members[identity].memberId,
          ending: { id: "conflicting-accounts", name: "矛盾的口供", outcome_text: "两人共同确认时间线存在冲突。" },
          chapters: Object.values(members).map((item) => ({
            id: `${item.characterId}-final-judgment`,
            character_id: item.characterId,
            title: `${item.characterName}·共同终判`,
            content: `${item.characterName}的完整复盘章节。`,
          })),
          truth: {
            case_summary: "照片和便签揭示两份解释无法同时成立。",
            murderer: null,
            victim: null,
            motive: null,
            timeline: [{ time: "22:10", event: "目击者听见走廊动静", hidden: false }],
            key_evidence_chain: ["抵达照片"],
            alternative_endings: [],
          },
          final_settlement: {
            stage_id: "final-judgment",
            settlement_id: "final-judgment",
            outcome_id: "conflicting-accounts",
            reveal: "outcome_only",
          },
        });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/scene-presence` && method === "PUT") {
        const body = request.postDataJSON() as PresencePayload;
        expect(Object.keys(body).sort()).toEqual(["facing", "moving", "x", "y"]);
        expect(body).not.toHaveProperty("member_id");
        expect(body).not.toHaveProperty("character_id");
        presenceBodies.push({ identity, body });
        presence.set(identity, {
          x: body.x,
          y: body.y,
          facing: body.facing,
          moving: body.moving,
        });
        return route.fulfill({ status: 204, body: "" });
      }
      if (pathname === `/api/v1/sessions/${sessionId}/commands` && method === "POST") {
        const body = request.postDataJSON();
        expect(body.command_id).toMatch(/^[0-9a-f-]{36}$/i);
        if (body.expected_revision !== revision) {
          return json(route, {
            command_id: body.command_id,
            status: "rejected",
            revision,
            event_sequence: eventSequence,
            result: null,
            error: { code: "REVISION_MISMATCH", message: "Refresh snapshot", details: {} },
            replayed: false,
          });
        }

        if (body.type === "stage.confirm_read" && phase === "read") {
          read.add(identity);
          readMembers.add(members[identity].memberId);
          if (read.size === 2) phase = "discuss";
        } else if (body.type === "discussion.send_message" && phase === "discuss") {
          if (messageFailures > 0) {
            messageFailures -= 1;
            return json(route, {
              command_id: body.command_id,
              status: "rejected",
              revision,
              event_sequence: eventSequence,
              result: null,
              error: { code: "TEMPORARY_FAILURE", message: "Message send failed", details: {} },
              replayed: false,
            });
          }
          eventSequence += 1;
          messages.push({
            sequence: eventSequence,
            message_id: body.payload.message_id,
            stage_id: stageId,
            member_id: members[identity].memberId,
            character_id: members[identity].characterId,
            text: body.payload.text,
          });
          return json(route, {
            command_id: body.command_id,
            status: "accepted",
            revision,
            event_sequence: eventSequence,
            result: { event_ids: [] },
            error: null,
            replayed: false,
          });
        } else if (body.type === "discussion.confirm_close" && phase === "discuss") {
          closed.add(identity);
          if (closed.size === 2) phase = "settle";
        } else if (body.type === "discussion.revoke_close" && phase === "discuss") {
          closed.delete(identity);
        } else if (body.type === "settlement.submit" && phase === "settle" && stageId === "investigation") {
          votes.set(identity, body.payload.option_id);
          if (votes.size === 2) phase = "reveal";
        } else if (body.type === "stage.advance" && phase === "reveal") {
          stageId = "final-judgment";
          phase = "read";
          read.clear();
          readMembers.clear();
          closed.clear();
        } else if (body.type === "settlement.confirm_shared_choice" && phase === "settle" && stageId === "final-judgment") {
          if (sharedOptionId !== body.payload.option_id) sharedConfirmations.clear();
          sharedOptionId = body.payload.option_id;
          sharedConfirmations.add(identity);
          if (sharedConfirmations.size === 2) {
            status = "completed";
            phase = "reveal";
            endingId = "conflicting-accounts";
          }
        } else {
          return json(route, {
            command_id: body.command_id,
            status: "rejected",
            revision,
            event_sequence: eventSequence,
            result: null,
            error: { code: "PHASE_MISMATCH", message: "Wrong phase", details: {} },
            replayed: false,
          });
        }

        revision += 1;
        eventSequence += 1;
        return json(route, {
          command_id: body.command_id,
          status: "accepted",
          revision,
          event_sequence: eventSequence,
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
    failNextMessage() {
      messageFailures = 1;
    },
    failNextReviews(identity: Identity, count = 3) {
      reviewFailures[identity] = count;
    },
    hidePublicMaterials() {
      publicMaterialsVisible = false;
    },
    presenceBodies,
  };
}

async function createPlayerPage(browser: Browser, api: ReturnType<typeof createGameplayApi>, identity: Identity) {
  const context = await browser.newContext();
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
  await expect(page.locator(".demo-objective-card").getByText(`当前阶段 · ${stageName} · ${phaseName}`, { exact: true })).toBeVisible({ timeout: 8_000 });
}

test("private chapters remain participant-safe inside the movable multiplayer scene", async ({ browser }) => {
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

    const publicArchiveEntry = host.page.getByRole("button", { name: "打开公开档案" });
    await expect(publicArchiveEntry).toBeVisible();
    await publicArchiveEntry.click();
    await expect(host.page.getByRole("heading", { name: "公开档案" })).toBeVisible();
    await expect(host.page.getByText("照片记录了抵达时刻。")).toBeVisible();
    await host.page.getByRole("button", { name: "关闭" }).click();

    await host.page.reload();
    await expectScenePhase(host.page, "核对口供", "阅读角色信息");
    const restoredArchiveEntry = host.page.getByRole("button", { name: "打开公开档案" });
    await expect(restoredArchiveEntry).toBeVisible();
    await restoredArchiveEntry.click();
    await expect(host.page.getByText("照片记录了抵达时刻。")).toBeVisible();

    api.hidePublicMaterials();
    await expect(restoredArchiveEntry).toHaveCount(0, { timeout: 8_000 });
    await expect(host.page.getByRole("heading", { name: "公开档案" })).toHaveCount(0);

    const hostScene = host.page.locator(".mansion-demo");
    const guestScene = guest.page.locator(".mansion-demo");
    const hostLocal = host.page.locator('[data-character-id="self-investigator"]');
    const guestLocal = guest.page.locator('[data-character-id="self-insider"]');
    const hostOnGuest = guest.page.locator('[data-character-id="member-member-host"]');
    const guestOnHost = host.page.locator('[data-character-id="member-member-guest"]');

    await expect(hostLocal).toHaveAttribute("data-avatar-character-id", "investigator");
    await expect(hostLocal).toHaveAttribute("data-outfit", "long-coat");
    await expect(hostLocal).toHaveAttribute("data-accessory", "keys");
    await expect(guestLocal).toHaveAttribute("data-avatar-character-id", "insider");
    await expect(guestLocal).toHaveAttribute("data-outfit", "soft-jacket");
    await expect(guestLocal).toHaveAttribute("data-accessory", "scarf");
    await expect(hostOnGuest).toBeVisible();
    await expect(guestOnHost).toBeVisible();
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
    const initialGuestRemoteY = Number(await guestOnHost.getAttribute("data-scene-y"));
    await guest.page.keyboard.down("KeyW");
    await guest.page.waitForTimeout(650);
    await guest.page.keyboard.up("KeyW");
    await expect.poll(async () => Number(await guestScene.getAttribute("data-player-y"))).toBeLessThan(initialGuestY);
    await expect.poll(
      async () => Number(await guestOnHost.getAttribute("data-scene-y")),
      { timeout: 8_000 },
    ).toBeLessThan(initialGuestRemoteY);

    expect(api.presenceBodies.some(({ identity }) => identity === "host")).toBe(true);
    expect(api.presenceBodies.some(({ identity }) => identity === "guest")).toBe(true);

    await host.page.getByRole("button", { name: "角色章" }).click();
    await guest.page.getByRole("button", { name: "角色章" }).click();
    await expect(host.page.getByText("调查员私有线索：照片时间可疑。")).toBeVisible();
    await expect(host.page.getByText("知情人私有线索：门锁一直完好。")).toHaveCount(0);
    await expect(guest.page.getByText("知情人私有线索：门锁一直完好。")).toBeVisible();
    await expect(guest.page.getByText("调查员私有线索：照片时间可疑。")).toHaveCount(0);

    await host.page.getByRole("button", { name: "我已读完" }).click();
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({ timeout: 8_000 });
    expect(host.webSockets).toEqual([]);
    expect(guest.webSockets).toEqual([]);
  } finally {
    await Promise.all([host.context.close(), guest.context.close()]);
  }
});
