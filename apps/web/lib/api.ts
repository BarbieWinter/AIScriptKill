/**
 * API 客户端封装
 * 统一的 fetch 封装 + 错误处理
 */

const API_BASE = "/api/v1";

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: any
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: any
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const options: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  const res = await fetch(url, options);

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      error.error?.code || "UNKNOWN_ERROR",
      error.error?.message || "请求失败",
      error.error?.details
    );
  }

  return res.json();
}

export const api = {
  // 会话
  createSession: (scriptId: string, characterId: string) =>
    request<any>("POST", "/sessions", {
      script_id: scriptId,
      preferred_character_id: characterId,
    }),

  getSession: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}`),

  // 游戏操作
  performAction: (sessionId: string, action: string, params: any) =>
    request<any>("POST", `/sessions/${sessionId}/actions`, {
      action,
      ...params,
    }),

  submitFinal: (sessionId: string, submission: any) =>
    request<any>("POST", `/sessions/${sessionId}/final-submission`, submission),

  // 数据查询
  getClues: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}/clues`),

  getEvidences: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}/evidences`),

  getCharacters: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}/characters`),

  getChatHistory: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}/chat-history`),

  getCards: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}/cards`),

  getReview: (sessionId: string) =>
    request<any>("GET", `/sessions/${sessionId}/review`),
};
