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
  private hasOpened = false;

  constructor(sessionId: string) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const baseUrl = process.env.NEXT_PUBLIC_WS_URL;
    this.url = baseUrl
      ? `${baseUrl.replace(/\/$/, "")}/api/v1/ws/${sessionId}`
      : `${protocol}//${window.location.host}/api/v1/ws/${sessionId}`;
  }

  connect() {
    if (
      this.destroyed ||
      this.ws?.readyState === WebSocket.CONNECTING ||
      this.ws?.readyState === WebSocket.OPEN
    ) {
      return;
    }
    const socket = new WebSocket(this.url);
    this.ws = socket;

    socket.onopen = () => {
      if (this.destroyed || this.ws !== socket) {
        socket.close();
        return;
      }
      this.hasOpened = true;
      console.info("[WS] 连接已建立");
      this.send("session.ping", {});
      this.startPing();
    };

    socket.onmessage = (event) => {
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

    socket.onclose = (event) => {
      if (this.ws === socket) this.ws = null;
      this.stopPing();
      if (this.destroyed) return;
      console.warn(`[WS] 连接已关闭，3 秒后重连（code=${event.code}）`);
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    socket.onerror = () => {
      if (this.destroyed || this.ws !== socket) return;
      // 浏览器不会提供可诊断的 Error 对象；关闭事件会携带 code 并负责重连。
      if (this.hasOpened) console.warn("[WS] 实时通道中断，等待自动重连");
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
    this.ws?.close(1000, "client disconnect");
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
