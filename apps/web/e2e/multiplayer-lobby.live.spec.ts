import { expect, test, type APIRequestContext, type Browser, type BrowserContext, type Page } from "@playwright/test";

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://127.0.0.1:8000";
const SCRIPT_ID = "mp1-two-player";

async function requireLiveResponse(
  request: APIRequestContext,
  path: string,
  description: string,
) {
  const response = await request.get(`${API_BASE_URL}${path}`);
  if (!response.ok()) {
    throw new Error(
      `MP-2 LIVE BLOCKED: ${description} (${response.status()} ${response.statusText()}).`,
    );
  }
  return response;
}

async function requireLivePrerequisites(request: APIRequestContext) {
  await requireLiveResponse(request, "/health/db", "FastAPI or its database is not ready");
  const response = await requireLiveResponse(
    request,
    "/api/v1/packages",
    "the published package inventory is unavailable",
  );
  const body = await response.json() as { packages?: Array<{ id?: string }> };
  if (!body.packages?.some((item) => item.id === SCRIPT_ID)) {
    throw new Error(
      `MP-2 LIVE BLOCKED: published runtime package ${SCRIPT_ID} is missing.`,
    );
  }
}

async function createLivePlayer(browser: Browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const applicationWebSockets: string[] = [];
  page.on("websocket", (socket) => {
    if (!socket.url().includes("/_next/")) applicationWebSockets.push(socket.url());
  });
  return { context, page, applicationWebSockets };
}

async function closeContexts(contexts: BrowserContext[]) {
  await Promise.all(contexts.map((context) => context.close()));
}

async function waitForPhase(page: Page, stageName: string, phaseName: string) {
  await expect(page.locator(".mansion-demo")).toBeVisible({ timeout: 10_000 });
  await expect(
    page.locator(".demo-objective-card").getByText(
      `当前阶段 · ${stageName} · ${phaseName}`,
      { exact: true },
    ),
  ).toBeVisible({ timeout: 10_000 });
}

async function openJournal(page: Page) {
  await page.getByRole("button", { name: "角色章" }).click();
}

async function closePanel(page: Page) {
  await page.getByRole("button", { name: "关闭" }).click();
}

async function confirmRead(page: Page) {
  await page.getByRole("button", { name: "我已读完" }).click();
}

async function confirmDiscussionClose(page: Page) {
  await page.getByRole("button", { name: "确认结束讨论" }).click();
}

async function chooseCharacter(page: Page, name: string) {
  await page.getByRole("button", { name: `选择角色 ${name}` }).click();
  await expect(page.getByRole("button", { name: `取消选择角色 ${name}` })).toBeVisible();
}

test.beforeAll(async ({ request }) => {
  await requireLivePrerequisites(request);
});

test("two real anonymous identities complete the M3 candidate game and review", async ({ browser }) => {
  test.setTimeout(240_000);
  const host = await createLivePlayer(browser);
  const guest = await createLivePlayer(browser);

  try {
    await host.page.goto("/multiplayer");
    await expect(host.page.getByRole("heading", { name: "双人剧本房间" })).toBeVisible();
    await host.page.getByRole("button", { name: "创建双人房间" }).click();
    await expect(host.page).toHaveURL(/\/play\/[0-9a-f-]+\/lobby$/i);
    await expect(host.page.getByRole("heading", { name: "房间大厅" })).toBeVisible();
    await expect(host.page.getByTestId("player-slot-2")).toContainText("等待玩家加入");

    await host.page.getByRole("button", { name: "创建 15 分钟邀请" }).click();
    const inviteUrl = await host.page.getByTestId("invite-url").textContent();
    expect(inviteUrl).toMatch(/\/invite\/[A-Za-z0-9._~-]+$/);

    await guest.page.goto(inviteUrl!);
    await expect(guest.page).toHaveURL(/\/play\/[0-9a-f-]+\/lobby$/i);
    await expect(guest.page.getByRole("heading", { name: "房间大厅" })).toBeVisible();
    await expect(host.page.getByTestId("player-slot-2")).toContainText("玩家 2", {
      timeout: 10_000,
    });

    await chooseCharacter(host.page, "调查员");
    await host.page.getByRole("button", { name: "准备", exact: true }).click();
    await expect(host.page.getByRole("button", { name: "取消准备" })).toBeVisible();

    await host.page.getByRole("button", { name: "取消选择角色 调查员" }).click();
    await expect(host.page.getByTestId("player-slot-1")).toContainText("未准备");
    await expect(host.page.getByTestId("player-slot-1")).toContainText("尚未选择");

    await chooseCharacter(host.page, "调查员");
    await host.page.getByRole("button", { name: "准备", exact: true }).click();
    await expect(host.page.getByRole("button", { name: "取消准备" })).toBeVisible();
    await expect(guest.page.getByTestId("player-slot-1")).toContainText("调查员", {
      timeout: 10_000,
    });
    await expect(guest.page.getByTestId("player-slot-1")).toContainText("已准备", {
      timeout: 10_000,
    });

    await chooseCharacter(guest.page, "知情人");
    await guest.page.getByRole("button", { name: "准备", exact: true }).click();
    await expect(guest.page.getByRole("button", { name: "取消准备" })).toBeVisible();

    const start = host.page.getByRole("button", { name: "开始游戏" });
    await expect(start).toBeEnabled({ timeout: 10_000 });
    await start.click();

    await waitForPhase(host.page, "核对口供", "阅读角色信息");
    await waitForPhase(guest.page, "核对口供", "阅读角色信息");

    const hostLocal = host.page.locator('[data-character-id="self-investigator"]');
    const guestLocal = guest.page.locator('[data-character-id="self-insider"]');
    const hostOnGuest = guest.page.locator('[data-avatar-character-id="investigator"]:not(.demo-character-player)');
    const guestOnHost = host.page.locator('[data-avatar-character-id="insider"]:not(.demo-character-player)');
    await expect(hostLocal).toHaveAttribute("data-outfit", "long-coat");
    await expect(hostLocal).toHaveAttribute("data-accessory", "keys");
    await expect(guestLocal).toHaveAttribute("data-outfit", "soft-jacket");
    await expect(guestLocal).toHaveAttribute("data-accessory", "scarf");
    await expect(hostOnGuest).toBeVisible({ timeout: 10_000 });
    await expect(guestOnHost).toBeVisible({ timeout: 10_000 });

    const hostScene = host.page.locator(".mansion-demo");
    const guestScene = guest.page.locator(".mansion-demo");
    const hostRemoteStartX = Number(await hostOnGuest.getAttribute("data-scene-x"));
    const guestRemoteStartY = Number(await guestOnHost.getAttribute("data-scene-y"));
    await host.page.keyboard.down("KeyD");
    await host.page.waitForTimeout(650);
    await host.page.keyboard.up("KeyD");
    await expect.poll(
      async () => Number(await hostOnGuest.getAttribute("data-scene-x")),
      { timeout: 12_000 },
    ).toBeGreaterThan(hostRemoteStartX);
    await guest.page.keyboard.down("KeyW");
    await guest.page.waitForTimeout(650);
    await guest.page.keyboard.up("KeyW");
    await expect.poll(
      async () => Number(await guestOnHost.getAttribute("data-scene-y")),
      { timeout: 12_000 },
    ).toBeLessThan(guestRemoteStartY);
    await expect(hostScene).toHaveAttribute("data-player-x", /\d+/);
    await expect(guestScene).toHaveAttribute("data-player-y", /\d+/);

    await openJournal(host.page);
    await openJournal(guest.page);
    await expect(host.page.getByTestId("chapter-investigator-investigation")).toBeVisible();
    await expect(host.page.getByTestId("chapter-insider-investigation")).toHaveCount(0);
    await expect(guest.page.getByTestId("chapter-insider-investigation")).toBeVisible();
    await expect(guest.page.getByTestId("chapter-investigator-investigation")).toHaveCount(0);

    await confirmRead(host.page);
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await confirmRead(guest.page);
    await waitForPhase(host.page, "核对口供", "公开讨论");
    await waitForPhase(guest.page, "核对口供", "公开讨论");

    await closePanel(host.page);
    await closePanel(guest.page);
    await host.page.getByRole("button", { name: "打开讨论" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    await host.page.getByRole("textbox", { name: "讨论消息", exact: true }).fill("门锁没有损坏。");
    await host.page.getByRole("button", { name: "发送讨论消息" }).click();
    await expect(guest.page.getByText("门锁没有损坏。")).toBeVisible({ timeout: 10_000 });

    await confirmDiscussionClose(host.page);
    await expect(guest.page.getByText("1/2 确认", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await confirmDiscussionClose(guest.page);
    await expect(host.page.getByRole("button", { name: "打开判断" })).toBeVisible({
      timeout: 10_000,
    });
    await host.page.getByRole("button", { name: "打开判断" }).click();
    await guest.page.getByRole("button", { name: "打开判断" }).click();
    await expect(
      host.page.getByRole("heading", { name: "二十点二十分的金属声最可能来自哪种情况？" }),
    ).toBeVisible({ timeout: 10_000 });

    await host.page.getByText("金属声本身不能证明破门，来源可能是值班室内已有的人或物", { exact: true }).click();
    await host.page.getByRole("button", { name: "确认选择" }).click();
    await expect(guest.page.getByText("1/2 位玩家已提交")).toBeVisible({ timeout: 10_000 });
    await guest.page.getByText("有人早已在室内，金属声来自钥匙掉落", { exact: true }).click();
    await guest.page.getByRole("button", { name: "确认选择" }).click();
    await expect(host.page.getByTestId("revealed-ballots")).toBeVisible({ timeout: 10_000 });

    await host.page.getByRole("button", { name: "进入下一阶段" }).click();
    await waitForPhase(host.page, "共同终判", "阅读角色信息");
    await waitForPhase(guest.page, "共同终判", "阅读角色信息");
    await openJournal(host.page);
    await openJournal(guest.page);
    await expect(host.page.getByTestId("chapter-investigator-final-judgment")).toBeVisible();
    await expect(host.page.getByTestId("chapter-insider-final-judgment")).toHaveCount(0);
    await expect(guest.page.getByTestId("chapter-insider-final-judgment")).toBeVisible();
    await expect(guest.page.getByTestId("chapter-investigator-final-judgment")).toHaveCount(0);

    await confirmRead(host.page);
    await expect(guest.page.getByText("1/2 已读", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await confirmRead(guest.page);
    await waitForPhase(host.page, "共同终判", "公开讨论");
    await waitForPhase(guest.page, "共同终判", "公开讨论");
    await closePanel(host.page);
    await closePanel(guest.page);
    await host.page.getByRole("button", { name: "打开讨论" }).click();
    await guest.page.getByRole("button", { name: "打开讨论" }).click();
    await confirmDiscussionClose(host.page);
    await expect(guest.page.getByText("1/2 确认", { exact: true })).toBeVisible({
      timeout: 10_000,
    });
    await confirmDiscussionClose(guest.page);
    await expect(host.page.getByRole("button", { name: "打开判断" })).toBeVisible({
      timeout: 10_000,
    });
    await host.page.getByRole("button", { name: "打开判断" }).click();
    await guest.page.getByRole("button", { name: "打开判断" }).click();

    await expect(
      host.page.getByRole("heading", { name: "现有材料与公开口供支持哪一道责任边界？" }),
    ).toBeVisible({ timeout: 10_000 });
    await host.page.getByText("认定知情人违规进入并隐瞒，但没有证据证明其破门或损毁记录", { exact: true }).click();
    await host.page.getByRole("button", { name: "确认选择" }).click();
    await expect(guest.page.getByText("1/2 位玩家已提交")).toBeVisible({ timeout: 10_000 });
    await guest.page.getByText("认定知情人违规进入并隐瞒，但没有证据证明其破门或损毁记录", { exact: true }).click();
    await guest.page.getByRole("button", { name: "确认选择" }).click();
    await closePanel(host.page);
    await closePanel(guest.page);

    for (const player of [host, guest]) {
      await expect(player.page.getByText("当前阶段 · 游戏完成", { exact: true })).toBeVisible({
        timeout: 10_000,
      });
      await player.page.getByRole("button", { name: "打开复盘" }).click();
      await expect(player.page.getByRole("heading", { name: "案件复盘" })).toBeVisible({
        timeout: 10_000,
      });
      await expect(player.page.getByRole("heading", { name: "责任止于证据" })).toBeVisible({
        timeout: 10_000,
      });
      await expect(player.page.getByRole("heading", { name: "案件真相" })).toBeVisible();
      await expect(
        player.page.getByText(/知情人于二十点零五分违规使用备用钥匙/),
      ).toBeVisible();
    }

    expect(host.applicationWebSockets).toEqual([]);
    expect(guest.applicationWebSockets).toEqual([]);
  } finally {
    await closeContexts([host.context, guest.context]);
  }
});
