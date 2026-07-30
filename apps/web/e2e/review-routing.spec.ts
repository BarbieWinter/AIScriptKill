import { expect, test, type Route } from "@playwright/test";

const legacySessionId = "22222222-2222-4222-8222-222222222222";
const legacyReview = {
  session_id: legacySessionId,
  script_id: "snow-village",
  score: 88,
  max_score: 100,
  rating: "A",
  duration_minutes: 42,
  breakdown: {
    suspect_correct: true,
    motive_correct: true,
    key_evidence_hit_rate: "4/5",
    wrong_accusations: 0,
    hints_used: 1,
    total_clues_found: 4,
    total_clues_available: 5,
    clue_coverage: "80%",
  },
  missed_key_clues: [],
  optimal_path: ["核对时间线", "确认门锁记录"],
  player_path: ["确认门锁记录"],
  truth_summary: "旧版单人复盘仍可在多人匿名身份不可用时读取。",
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

test("legacy review errors stay on the legacy path instead of falling through to multiplayer", async ({ page }) => {
  let legacyReviewRequests = 0;

  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === `/api/v1/sessions/${legacySessionId}/review`) {
      legacyReviewRequests += 1;
      await json(route, {
        error: { code: "TEMPORARY_FAILURE", message: "旧版复盘暂时不可用", details: {} },
      }, 500);
      return;
    }
    await json(route, { error: { code: "NOT_FOUND", message: pathname, details: {} } }, 404);
  });

  await page.goto(`/play/${legacySessionId}/review`);
  await expect(page.getByRole("alert").filter({ hasText: "旧版复盘暂时不可用" })).toBeVisible({ timeout: 8_000 });
  expect(legacyReviewRequests).toBe(3);
});

test("legacy UUID review falls back without anonymous auth and returns to library", async ({ context, page }) => {
  let signupRequests = 0;
  let legacyReviewRequests = 0;
  let releaseLegacyReview!: () => void;
  const legacyReviewGate = new Promise<void>((resolve) => {
    releaseLegacyReview = resolve;
  });

  await context.route("**/auth/v1/signup", async (route) => {
    signupRequests += 1;
    await json(route, { message: "Anonymous sign-in unavailable" }, 503);
  });
  await context.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname === `/api/v1/sessions/${legacySessionId}/review`) {
      legacyReviewRequests += 1;
      expect(request.headers().authorization).toBeUndefined();
      await legacyReviewGate;
      await json(route, legacyReview);
      return;
    }
    await json(route, { error: { code: "NOT_FOUND", message: pathname, details: {} } }, 404);
  });

  await page.goto(`/play/${legacySessionId}/review`);
  await expect(page.getByText("正在读取终局复盘…", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /返回(终局|剧本库|多人入口)/ })).toHaveCount(0);

  expect(signupRequests).toBe(0);
  releaseLegacyReview();
  await expect(page.getByText("88", { exact: true })).toBeVisible({ timeout: 8_000 });
  await expect(page.getByText(legacyReview.truth_summary, { exact: true })).toBeVisible();
  await expect(page.getByText("案件复盘", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("link", { name: "返回剧本库" })).toHaveAttribute("href", "/library");
  expect(signupRequests).toBe(0);
  expect(legacyReviewRequests).toBe(1);
});
