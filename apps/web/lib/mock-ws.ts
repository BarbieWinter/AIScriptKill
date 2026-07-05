/**
 * Mock WebSocket 客户端
 * 模拟真实后端 WebSocket 行为，无需真实连接
 *
 * 完全遵循 API_REFERENCE.md WebSocket 协议定义
 */

import { getMockEngine } from "./mock-data";

type WsEventHandler = (data: any) => void;

/**
 * Mock WebSocket 客户端
 * 模拟服务端事件推送，支持：
 * - chat.message（NPC 回复模拟）
 * - stage.changed（阶段切换）
 * - clue.unlocked（线索解锁）
 * - evidence.discovered（证物发现）
 * - npc.state_changed（角色状态变化）
 * - media.play（媒体播放指令）
 * - hint.shown（提示推送）
 */
export class MockWsClient {
  private handlers: Map<string, WsEventHandler[]> = new Map();
  private destroyed = false;
  private simulatedDelay = 1500; // 模拟 LLM 响应延迟(ms)
  private hintTimers: ReturnType<typeof setTimeout>[] = [];
  private engine = getMockEngine();

  constructor(_sessionId: string) {
    // 模拟构造函数
  }

  /** 连接（模拟） */
  connect() {
    if (this.destroyed) return;
    console.log("[MockWS] 连接已建立");

    // 模拟欢迎消息
    setTimeout(() => {
      this.emit("chat.message", {
        id: "msg-0",
        role: "npc",
        character_id: "dm",
        text: "欢迎来到雪乡连环杀人事件。你是新来的游客吧？夜色已深，不如先去村口的饭店落脚？",
        emotion: "calm",
        timestamp: new Date().toISOString(),
      });
    }, 500);

    // 模拟3分钟后提示（如果还在同一场景）
    this.hintTimers.push(
      setTimeout(() => {
        this.emit("hint.shown", {
          text: "试试和王大达聊聊，他看起来知道些什么。",
          remaining_hints: 3,
        });
      }, 30000)
    );
  }

  /** 订阅事件 */
  on(eventType: string, handler: WsEventHandler) {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, []);
    }
    this.handlers.get(eventType)!.push(handler);
    return () => this.off(eventType, handler);
  }

  /** 取消订阅 */
  off(eventType: string, handler: WsEventHandler) {
    const handlers = this.handlers.get(eventType);
    if (handlers) {
      const idx = handlers.indexOf(handler);
      if (idx >= 0) handlers.splice(idx, 1);
    }
  }

  /** 发送消息（模拟） */
  send(type: string, data: any) {
    if (this.destroyed) return;

    switch (type) {
      case "chat.send": {
        const { character_id, text } = data;

        // 模拟 NPC 正在输入
        this.emit("npc.state_changed", {
          character_id,
          emotion: "thinking",
          emotion_description: `${character_id === "dm" ? "DM" : getCharacterName(character_id)}正在思索……`,
          trust_level: 50,
          tension_level: 30,
        });

        // 延迟后回复
        setTimeout(() => {
          if (this.destroyed) return;
          const response = this.engine.sendMessage(character_id, text);
          if (response) {
            this.emit("chat.message", {
              id: `msg-${Date.now()}`,
              role: "npc",
              character_id,
              text: response.text,
              emotion: response.emotion,
              timestamp: new Date().toISOString(),
            });

            // 状态变化
            this.emit("npc.state_changed", {
              character_id,
              emotion: response.emotion,
              emotion_description: getEmotionDescription(response.emotion),
              trust_level: 50 + (response.state_changes.trust || 0),
              tension_level: 30 + (response.state_changes.nervous || response.state_changes.fear || 0),
            });
          }
        }, this.simulatedDelay);

        break;
      }

      case "action.perform": {
        const { action, params } = data;
        this.handleAction(action, params);
        break;
      }

      case "session.ping": {
        // 模拟 pong（不需要事件）
        break;
      }
    }
  }

  /**
   * 处理游戏操作（模拟）
   * 对应 API_REFERENCE.md 2.2 節
   */
  private handleAction(action: string, params: any) {
    switch (action) {
      case "examine_scene": {
        const result = this.engine.examineScene(params.scene_id, params.hotspot_id);

        // DM叙述
        this.emit("chat.message", {
          id: `msg-${Date.now()}`,
          role: "npc",
          character_id: "dm",
          text: result.dm_narration,
          emotion: "calm",
          timestamp: new Date().toISOString(),
        });

        // 解锁的线索
        result.discovered_clues?.forEach((clue: any) => {
          setTimeout(() => {
            if (!this.destroyed) {
              this.emit("clue.unlocked", {
                clue_id: clue.id,
                name: clue.name,
                image_url: clue.image_url || "",
                description: clue.description,
                is_key: clue.is_key,
              });
            }
          }, 500);
        });

        // 发现的证物
        result.discovered_evidences?.forEach((ev: any) => {
          setTimeout(() => {
            if (!this.destroyed) {
              this.emit("evidence.discovered", {
                evidence_id: ev.id,
                name: ev.name,
                image_url: ev.image_url || "",
              });
            }
          }, 800);
        });

        // 音效
        result.media_triggers?.forEach((t: any) => {
          this.emit("media.play", {
            asset_id: t.asset_id,
            type: "sfx",
            url: "",
            volume: 0.4,
            skip_allowed: true,
            options: { block_input: false, auto_advance: false },
          });
        });
        break;
      }

      case "show_evidence": {
        const result = this.engine.showEvidence(params.character_id, params.evidence_id);

        this.emit("chat.message", {
          id: `msg-${Date.now()}`,
          role: "npc",
          character_id: params.character_id,
          text: result.text,
          emotion: result.emotion,
          timestamp: new Date().toISOString(),
        });

        this.emit("npc.state_changed", {
          character_id: params.character_id,
          emotion: result.emotion,
          emotion_description: getEmotionDescription(result.emotion),
          trust_level: 50 + (result.state_changes?.trust || 0),
          tension_level: 30 + (result.state_changes?.fear || result.state_changes?.nervous || 0),
        });

        result.media_triggers?.forEach((t: any) => {
          this.emit("media.play", {
            asset_id: t.asset_id,
            type: "sfx",
            url: "",
            volume: 0.4,
            skip_allowed: true,
            options: { block_input: false, auto_advance: false },
          });
        });
        break;
      }

      case "request_advance": {
        const result = this.engine.requestAdvance(params.reason || "");

        if (result.type === "stage_transition") {
          // 延迟后触发阶段切换
          setTimeout(() => {
            if (!this.destroyed) {
              this.emit("stage.changed", {
                from: result.from_stage,
                to: result.to_stage,
                stage_name: result.stage_name,
                reason: params.reason || "线索收集完成",
                available_actions: result.new_state.available_actions,
                available_characters: result.new_state.available_characters,
              });

              // 切换场景
              this.emit("media.bgm_change", {
                from: "bgm_investigation",
                to: "bgm_tension",
                crossfade: 3.0,
              });
            }
          }, 1000);
        } else {
          // 拒绝推进
          this.emit("hint.shown", {
            text: result.hint,
            remaining_hints: 2,
          });
        }
        break;
      }
    }
  }

  /** 内部触发事件 */
  private emit(eventType: string, data: any) {
    if (this.destroyed) return;
    const eventHandlers = this.handlers.get(eventType);
    if (eventHandlers) {
      eventHandlers.forEach((handler) => handler(data));
    }
  }

  /** 断开连接 */
  disconnect() {
    this.destroyed = true;
    this.hintTimers.forEach((t) => clearTimeout(t));
    this.hintTimers = [];
    console.log("[MockWS] 已断开");
  }
}

/** 获取角色中文名 */
function getCharacterName(charId: string): string {
  const names: Record<string, string> = {
    zhuosiyuan: "卓司元",
    cuikaiqiang: "崔铠强",
    likaixin: "李开心",
    wangqi: "王琪",
    xiaomeng: "萧萌",
    chenji: "陈吉",
    wangdada: "王大达",
    chengjun: "程俊",
    dm: "DM",
  };
  return names[charId] || charId;
}

/** 获取情绪描述 */
function getEmotionDescription(emotion: string): string {
  const descriptions: Record<string, string> = {
    normal: "表情平静，看不出什么异常",
    slightly_nervous: "表面上还在笑，但眼神有些飘忽",
    nervous: "说话有些结巴，额头上冒着细汗",
    defensive: "语气变得强硬，但似乎是在掩饰什么",
    cold: "面无表情，眼神冰冷",
    slightly_agitated: "显得有些烦躁，不愿多谈",
    shocked: "脸色大变，显然被你的话震惊了",
    fear: "脸色苍白，声音发颤，冷汗直流",
    sad: "眼神中流露出悲伤，仿佛想起了什么往事",
    thinking: "正在思考你的问题，眉头微皱",
    serious: "神情严肃，语气凝重",
    calm: "平静地叙述着",
    angry: "怒火中烧，拳头紧握",
    scared: "吓得后退了一步，声音发抖",
    lying: "眼神闪烁，不敢直视你",
  };
  return descriptions[emotion] || emotion;
}
