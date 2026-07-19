import { AnonymousSessionError } from "@/lib/auth/anonymous-session";
import { MultiplayerClientError } from "./room-client";

const stableMessages: Record<string, string> = {
  AUTH_REQUIRED: "登录状态已失效，请重试。",
  INVALID_TOKEN: "登录凭证无效，请刷新页面后重试。",
  INVALID_USER_ID: "玩家身份无效，请重新建立匿名会话。",
  ANONYMOUS_IDENTITY_REQUIRED: "多人房间目前仅支持匿名玩家身份。",
  MULTIPLAYER_DISABLED: "多人房间暂未开放。",
  UNFINISHED_ROOM_EXISTS: "你已有一个未结束的多人房间，请先继续该房间。",
  NOT_ROOM_MEMBER: "你不是该房间成员，无法查看房间内容。",
  HOST_REQUIRED: "只有房主可以执行此操作。",
  INVITE_NOT_FOUND: "邀请不存在或链接无效。",
  INVITE_EXPIRED: "邀请已过期，请让房主重新创建。",
  INVITE_REVOKED: "邀请已被房主撤销。",
  INVITE_EXHAUSTED: "邀请已被使用，不能再次加入。",
  ROOM_FULL: "房间已满，无法加入更多玩家。",
  ROOM_NOT_IN_LOBBY: "房间已离开大厅，不能执行此操作。",
  REVISION_MISMATCH: "房间刚刚发生变化，已为你刷新最新状态。",
  CHARACTER_ALREADY_ASSIGNED: "该角色刚刚被另一位玩家选择，请选择其他角色。",
  CHARACTER_REQUIRED: "请先选择角色。",
  CHARACTER_NOT_PLAYABLE: "该角色不可由玩家选择。",
  ROOM_NOT_FULL: "需要两位玩家都加入后才能开始。",
  ASSIGNMENTS_INCOMPLETE: "两位玩家都必须选择不同角色。",
  PLAYERS_NOT_READY: "两位玩家都准备后才能开始。",
  COMMAND_NOT_AVAILABLE: "当前状态下不能执行此操作。",
  AUTH_CONFIGURATION_MISSING: "缺少 Supabase 匿名登录配置。",
  AUTH_BOOTSTRAP_FAILED: "匿名登录失败，请稍后重试。",
  AUTH_SESSION_READ_FAILED: "无法恢复匿名登录状态，请重试。",
};

export function multiplayerErrorCode(error: unknown): string | null {
  if (error instanceof MultiplayerClientError || error instanceof AnonymousSessionError) {
    return error.code;
  }
  return null;
}

export function multiplayerErrorMessage(error: unknown): string {
  const code = multiplayerErrorCode(error);
  if (code && stableMessages[code]) return stableMessages[code];
  if (error instanceof Error && error.message) return error.message;
  return "请求失败，请稍后重试。";
}

export function shouldRetryMultiplayer(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  if (error instanceof AnonymousSessionError) return false;
  if (error instanceof MultiplayerClientError) {
    return error.status >= 500 && error.status !== 503;
  }
  return true;
}
