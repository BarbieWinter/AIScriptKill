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

async function chooseCharacter(page: Page, name: string) {
  await page.getByRole("button", { name: `选择角色 ${name}` }).click();
  await expect(page.getByRole("button", { name: `取消选择角色 ${name}` })).toBeVisible();
}

test.beforeAll(async ({ request }) => {
  await requireLivePrerequisites(request);
});

test("two real anonymous identities complete the MP-2 lobby flow", async ({ browser }) => {
  test.setTimeout(90_000);
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

    await chooseCharacter(guest.page, "知情人");
    await guest.page.getByRole("button", { name: "准备", exact: true }).click();
    await expect(guest.page.getByRole("button", { name: "取消准备" })).toBeVisible();

    const start = host.page.getByRole("button", { name: "开始游戏" });
    await expect(start).toBeEnabled({ timeout: 10_000 });
    await start.click();

    await expect(host.page.getByRole("heading", { name: "房间已原子启动" })).toBeVisible();
    await expect(host.page.getByText(/多人游戏运行时将在 MP-6 提供/)).toBeVisible();
    await expect(guest.page.getByRole("heading", { name: "房间已原子启动" })).toBeVisible({
      timeout: 10_000,
    });

    expect(host.applicationWebSockets).toEqual([]);
    expect(guest.applicationWebSockets).toEqual([]);
  } finally {
    await closeContexts([host.context, guest.context]);
  }
});
