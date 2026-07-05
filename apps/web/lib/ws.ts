/**
 * WebSocket 客户端
 * 与后端引擎实时通信，支持自动重连
 */

type WsEventHandler = (data: any) => void;

export class WsClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Map<string, WsEventHandler[]> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private destroyed = false;

  constructor(sessionId: string) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    this.url = `${protocol}//${host}/api/v1/ws/${sessionId}`;
  }

  connect() {
    if (this.destroyed) return;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log("[WS] 连接已建立");
      this.startPing();
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const eventHandlers = this.handlers.get(message.type);
        if (eventHandlers) {
          eventHandlers.forEach((handler) => handler(message.data));
        }
      } catch (e) {
        console.error("[WS] 消息解析失败:", e);
      }
    };

    this.ws.onclose = () => {
      console.log("[WS] 连接已关闭");
      this.stopPing();
      // 自动重连（3 秒后）
      if (!this.destroyed) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    };

    this.ws.onerror = (err) => {
      console.error("[WS] 连接错误:", err);
    };
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

  /** 发送消息 */
  send(type: string, data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }

  /** 断开连接 */
  disconnect() {
    this.destroyed = true;
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  private startPing() {
    this.pingTimer = setInterval(() => {
      this.send("session.ping", {});
    }, 30000); // 每 30 秒心跳
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }
}
