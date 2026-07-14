/**
 * API 客户端封装
 *
 * 统一的 fetch 封装 + 错误处理 + Mock 模式支持
 * 开发环境默认使用 Mock 数据，生产环境连接真实后端
 *
 * 所有方法签名与 API_REFERENCE.md 完全一致
 * 每个方法均包含完整 JSDoc 说明
 */

import {
  mockPackages,
  mockCharacters,
  mockStages,
  mockClues,
  getMockEngine,
  resetMockEngine,
} from "./mock-data";

const API_BASE = "/api/v1";

/** 是否使用 Mock 数据（默认开发环境为 true） */
const USE_MOCK =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_USE_MOCK !== "false"
    : false;

export const isMockMode = () => USE_MOCK;

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
  // ══════════════════════════════════════════
  //  会话管理
  // ══════════════════════════════════════════

  /**
   * 创建游戏会话
   * POST /sessions
   *
   * @param scriptId - 剧本包 ID
   * @param characterId - 玩家选择的角色 ID
   * @param playerName - 玩家昵称（可选）
   * @returns 会话信息，包含 session_id、current_stage、available_actions 等
   */
  createSession: async (
    scriptId: string,
    characterId: string,
    playerName?: string
  ): Promise<{
    session_id: string;
    script_id: string;
    status: string;
    current_stage: string;
    player_character_id: string;
    available_actions: string[];
    created_at: string;
  }> => {
    if (USE_MOCK) {
      resetMockEngine();
      return {
        session_id: "mock-session-" + Date.now(),
        script_id: scriptId,
        status: "in_progress",
        current_stage: "prologue",
        player_character_id: characterId,
        available_actions: ["talk_to_npc", "open_clue_board"],
        created_at: new Date().toISOString(),
      };
    }
    return request("POST", "/sessions", {
      script_id: scriptId,
      preferred_character_id: characterId,
      player_name: playerName,
    });
  },

  /**
   * 获取会话状态
   * GET /sessions/{session_id}
   *
   * @param sessionId - 会话 ID
   * @returns 当前会话完整状态
   */
  getSession: async (
    sessionId: string
  ): Promise<{
    session_id: string;
    script_id: string;
    status: string;
    current_stage: string;
    stage_name: string;
    player_character_id: string;
    available_actions: string[];
    available_characters: string[];
    unlocked_clues_count: number;
    total_clues_in_round: number;
    discovered_evidences: string[];
    viewed_evidences: string[];
    current_scene: string;
    pending_media: Array<{ id: string; type: string; status: string }>;
  }> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      const stage = engine.getStage();
      const scene = engine.getCurrentScene();
      return {
        session_id: sessionId,
        script_id: "snow-village",
        status: "in_progress",
        current_stage: stage.id,
        stage_name: stage.name,
        player_character_id: "zhuosiyuan",
        available_actions: stage.available_actions as string[],
        available_characters: stage.available_characters,
        unlocked_clues_count: engine.getUnlockedClues().length,
        total_clues_in_round: mockClues.filter((c) => c.stage === stage.id).length,
        discovered_evidences: engine.getDiscoveredEvidences().map((item) => item.id),
        viewed_evidences: [],
        current_scene: scene.id,
        pending_media: [],
      };
    }
    return request("GET", `/sessions/${sessionId}`);
  },

  /**
   * 更新会话（存档/恢复操作）
   * PATCH /sessions/{session_id}
   *
   * @param sessionId - 会话 ID
   * @param action - 操作类型（restore/save）
   * @param checkpointId - 存档点 ID（恢复时必填）
   */
  updateSession: async (
    sessionId: string,
    action: string,
    checkpointId?: string
  ): Promise<any> => {
    if (USE_MOCK) {
      return {
        session_id: sessionId,
        status: "restored",
        current_stage: "act1_investigation",
        restored_from: checkpointId || null,
      };
    }
    return request("PATCH", `/sessions/${sessionId}`, {
      action,
      checkpoint_id: checkpointId,
    });
  },

  // ══════════════════════════════════════════
  //  游戏操作
  // ══════════════════════════════════════════

  /**
   * 执行游戏操作
   * POST /sessions/{sessionId}/actions
   *
   * 支持的操作类型：
   * - talk_to_npc: 与 NPC 对话
   * - examine_scene: 调查场景热点
   * - show_evidence: 向角色出示证物
   * - use_card: 使用卡牌
   * - request_advance: 请求推进阶段
   *
   * @param sessionId - 会话 ID
   * @param action - 操作类型
   * @param params - 操作参数（根据操作类型不同）
   * @returns 操作结果
   */
  performAction: async (
    sessionId: string,
    action: string,
    params: any
  ): Promise<any> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      switch (action) {
        case "examine_scene":
          return engine.examineScene(params.scene_id, params.hotspot_id);
        case "show_evidence":
          return engine.showEvidence(params.character_id, params.evidence_id);
        case "request_advance":
          return engine.requestAdvance(params.reason || "");
        default:
          return { type: "ack", action, status: "ok" };
      }
    }
    return request("POST", `/sessions/${sessionId}/actions`, {
      action,
      ...params,
    });
  },

  /** 提交雪乡首个切片的确定性阶段判断。 */
  submitFinal: async (
    sessionId: string,
    submission: { option: "A" | "B" | "C" | "D" }
  ): Promise<{
    type: "submission_result";
    correct: boolean;
    score: number;
    detail: {
      selected_option: "A" | "B" | "C" | "D";
      correct_option: "C";
      evidence_boundary: string;
      npc_disclosure: string | null;
    };
    ending_id: string;
    triggered_events: Array<{
      action: string;
      asset_id?: string;
      text?: string;
    }>;
  }> => {
    if (USE_MOCK) {
      const correct = submission.option === "C";
      return {
        type: "submission_result",
        correct,
        score: correct ? 100 : 0,
        detail: {
          selected_option: submission.option,
          correct_option: "C",
          evidence_boundary: correct
            ? "后门半开是已证实事实，但开门者和目的仍不可确认。"
            : "这项判断超出了当前材料能够证实的范围。",
          npc_disclosure: correct
            ? "后门当时确实开着。我后来发现门闩没扣严，就重新扣好了；我没看见是谁开的。"
            : null,
        },
        ending_id: correct
          ? "back_door_judgement_supported"
          : "back_door_judgement_unsupported",
        triggered_events: [],
      };
    }
    return request("POST", `/sessions/${sessionId}/final-submission`, submission);
  },

  // ══════════════════════════════════════════
  //  数据查询
  // ══════════════════════════════════════════

  /**
   * 获取已解锁线索列表
   * GET /sessions/{sessionId}/clues
   *
   * @param sessionId - 会话 ID
   * @returns 线索列表
   */
  getClues: async (sessionId: string): Promise<{ clues: any[] }> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      return { clues: engine.getUnlockedClues() };
    }
    return request("GET", `/sessions/${sessionId}/clues`);
  },

  /**
   * 获取已发现证物列表
   * GET /sessions/{sessionId}/evidences
   *
   * @param sessionId - 会话 ID
   * @returns 证物列表
   */
  getEvidences: async (sessionId: string): Promise<{ evidences: any[] }> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      return { evidences: engine.getDiscoveredEvidences() };
    }
    return request("GET", `/sessions/${sessionId}/evidences`);
  },

  /** 标记一件已发现证物为已查看。 */
  viewEvidence: async (
    sessionId: string,
    evidenceId: string
  ): Promise<{ evidence_id: string; status: string }> => {
    if (USE_MOCK) {
      return { evidence_id: evidenceId, status: "viewed" };
    }
    return request(
      "POST",
      `/sessions/${sessionId}/evidences/${encodeURIComponent(evidenceId)}/viewed`
    );
  },

  /** 获取当前玩家角色已解锁的人物章节。 */
  getCharacterChapters: async (
    sessionId: string
  ): Promise<{
    chapters: Array<{
      id: string;
      character_id: string;
      order: number;
      title: string;
      status: string;
    }>;
  }> => {
    if (USE_MOCK) return { chapters: [] };
    return request("GET", `/sessions/${sessionId}/character-chapters`);
  },

  /** 读取授权章节正文，并在服务端持久化已读状态。 */
  readCharacterChapter: async (
    sessionId: string,
    chapterId: string
  ): Promise<{
    id: string;
    character_id: string;
    order: number;
    title: string;
    status: string;
    content: string;
  }> => {
    if (USE_MOCK) {
      return {
        id: chapterId,
        character_id: "zhuosiyuan",
        order: 1,
        title: "人物章节",
        status: "viewed",
        content: "Mock 模式的人物章节由旧交互流程提供。",
      };
    }
    return request(
      "GET",
      `/sessions/${sessionId}/character-chapters/${encodeURIComponent(chapterId)}`
    );
  },

  /**
   * 获取当前场景角色
   * GET /sessions/{sessionId}/characters
   *
   * @param sessionId - 会话 ID
   * @returns 角色列表（含当前情绪）
   */
  getCharacters: async (
    sessionId: string
  ): Promise<{
    characters: Array<{
      id: string;
      name: string;
      portrait_url: string;
      current_mood: string;
      mood_description: string;
      dialogue_available: boolean;
    }>;
  }> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      const stage = engine.getStage();
      const available = stage.available_characters;
      const allChars = mockCharacters.filter(
        (c) => available.includes(c.id) || c.playable
      );
      return {
        characters: allChars.map((c) => ({
          id: c.id,
          name: c.name,
          portrait_url: c.portrait_url || "",
          current_mood: "normal",
          mood_description: "表情平静",
          dialogue_available: !c.playable,
        })),
      };
    }
    return request("GET", `/sessions/${sessionId}/characters`);
  },

  /**
   * 获取聊天记录
   * GET /sessions/{sessionId}/chat-history
   *
   * @param sessionId - 会话 ID
   * @returns 聊天消息列表
   */
  getChatHistory: async (
    sessionId: string
  ): Promise<{ messages: any[]; next_page_token?: string }> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      return {
        messages: engine.chatHistory,
      };
    }
    return request("GET", `/sessions/${sessionId}/chat-history`);
  },

  /**
   * 获取可用卡牌
   * GET /sessions/{sessionId}/cards
   *
   * @param sessionId - 会话 ID
   * @returns 卡牌列表
   */
  getCards: async (
    sessionId: string
  ): Promise<{
    cards: Array<{
      id: string;
      name: string;
      type: string;
      image_url: string;
      description: string;
      max_uses: number;
      remaining_uses: number;
      available: boolean;
    }>;
  }> => {
    if (USE_MOCK) {
      return {
        cards: [
          {
            id: "interrogation_card",
            name: "质问卡",
            type: "skill",
            image_url: "",
            description: "严厉质问一个角色，使其紧张度大幅上升",
            max_uses: 3,
            remaining_uses: 2,
            available: true,
          },
          {
            id: "empathy_card",
            name: "共情卡",
            type: "skill",
            image_url: "",
            description: "与角色共情，提升信任度",
            max_uses: 2,
            remaining_uses: 1,
            available: true,
          },
        ],
      };
    }
    return request("GET", `/sessions/${sessionId}/cards`);
  },

  /**
   * 获取复盘数据
   * GET /sessions/{sessionId}/review
   *
   * @param sessionId - 会话 ID
   * @returns 复盘评分数据
   */
  getReview: async (
    sessionId: string
  ): Promise<{
    session_id: string;
    script_id: string;
    score: number;
    max_score: number;
    rating: string;
    duration_minutes: number;
    breakdown: any;
    missed_key_clues: any[];
    optimal_path: string[];
    player_path: string[];
    truth_summary: string;
  }> => {
    if (USE_MOCK) {
      const engine = getMockEngine();
      return engine.getReview();
    }
    return request("GET", `/sessions/${sessionId}/review`);
  },

  // ══════════════════════════════════════════
  //  剧本包管理
  // ══════════════════════════════════════════

  /**
   * 获取剧本包列表（前台选本）
   * GET /packages
   *
   * @returns 已发布的剧本包列表
   */
  getPackages: async (): Promise<{ packages: any[] }> => {
    if (USE_MOCK) {
      return { packages: mockPackages };
    }
    return request("GET", "/packages");
  },

  /**
   * 获取剧本包详情
   * GET /packages/{packageId}
   *
   * @param packageId - 剧本包 ID
   * @returns 剧本包完整信息
   */
  getPackage: async (packageId: string): Promise<any> => {
    if (USE_MOCK) {
      const pkg = mockPackages.find((p) => p.id === packageId);
      if (!pkg) throw new ApiError(404, "SCRIPT_NOT_FOUND", "剧本包不存在");
      return {
        ...pkg,
        characters: mockCharacters,
        stages: mockStages,
      };
    }
    return request("GET", `/packages/${packageId}`);
  },
};
