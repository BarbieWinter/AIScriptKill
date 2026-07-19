import type { Session } from "@supabase/supabase-js";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export class AnonymousSessionError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AnonymousSessionError";
  }
}

let browserClient: SupabaseClient | null = null;
let bootstrapPromise: Promise<string> | null = null;

function getBrowserClient(): SupabaseClient {
  if (typeof window === "undefined") {
    throw new AnonymousSessionError(
      "AUTH_BROWSER_REQUIRED",
      "匿名登录只能在浏览器中初始化。",
    );
  }

  if (browserClient) return browserClient;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !publishableKey) {
    throw new AnonymousSessionError(
      "AUTH_CONFIGURATION_MISSING",
      "缺少 Supabase 匿名登录配置。",
    );
  }

  browserClient = createClient(url, publishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: false,
      persistSession: true,
    },
  });
  return browserClient;
}

function accessTokenFrom(session: Session | null): string | null {
  if (!session?.access_token) return null;
  if (session.user.is_anonymous !== true) {
    throw new AnonymousSessionError(
      "ANONYMOUS_IDENTITY_REQUIRED",
      "多人房间目前仅支持匿名玩家身份。",
    );
  }
  return session.access_token;
}

async function bootstrapAnonymousSession(): Promise<string> {
  const client = getBrowserClient();
  const { data: existing, error: existingError } = await client.auth.getSession();
  if (existingError) {
    throw new AnonymousSessionError(
      "AUTH_SESSION_READ_FAILED",
      existingError.message || "无法读取匿名登录状态。",
    );
  }

  const existingToken = accessTokenFrom(existing.session);
  if (existingToken) return existingToken;

  const { data, error } = await client.auth.signInAnonymously();
  if (error) {
    throw new AnonymousSessionError(
      "AUTH_BOOTSTRAP_FAILED",
      error.message || "匿名登录失败，请稍后重试。",
    );
  }

  const token = accessTokenFrom(data.session);
  if (!token) {
    throw new AnonymousSessionError(
      "AUTH_BOOTSTRAP_FAILED",
      "匿名登录未返回有效会话。",
    );
  }
  return token;
}

/** Reuses/refeshes a persisted anonymous session and deduplicates concurrent bootstraps. */
export async function getAnonymousAccessToken(): Promise<string> {
  if (!bootstrapPromise) {
    bootstrapPromise = bootstrapAnonymousSession();
  }

  const pending = bootstrapPromise;
  try {
    return await pending;
  } finally {
    if (bootstrapPromise === pending) bootstrapPromise = null;
  }
}
