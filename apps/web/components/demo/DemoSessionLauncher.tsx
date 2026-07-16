"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Database, Play, RotateCcw } from "lucide-react";
import { toast } from "sonner";

export function DemoSessionLauncher() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");
  const [creating, setCreating] = useState(false);

  const resume = () => {
    const value = sessionId.trim();
    if (!value) return;
    router.push(`/demo/live/${encodeURIComponent(value)}`);
  };

  const createLive = async () => {
    if (creating) return;
    setCreating(true);
    try {
      const response = await fetch("/api/v1/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          script_id: "snow-village",
          preferred_character_id: "zhuosiyuan",
          player_name: "卓司元",
        }),
      });
      if (!response.ok) throw new Error("无法创建真实会话");
      const session = await response.json() as { session_id: string };
      router.push(`/demo/live/${encodeURIComponent(session.session_id)}`);
    } catch (error) {
      console.error("[DemoSessionLauncher] 创建真实会话失败:", error);
      toast.error("无法创建真实游戏会话", {
        description: "请确认 API、数据库以及已发布的雪乡剧本包已就绪。",
      });
    } finally {
      setCreating(false);
    }
  };

  const createMock = () => {
    const id = `mock-session-${Date.now()}`;
    router.push(`/demo/mock/${id}`);
  };

  return (
    <section className="demo-session-launcher" aria-label="游戏数据入口">
      <span>GAME DATA CONNECTION</span>
      <h2>接入真实剧情数据</h2>
      <p>地图视觉保持不变；线索、证物、人物章节与剧情阶段由 Session API、YAML 包和 LangGraph 状态提供。</p>
      <div className="demo-session-launch-actions">
        <button type="button" className="is-primary" onClick={() => void createLive()} disabled={creating}>
          <Database /> {creating ? "创建中…" : "创建 Live 会话"}
        </button>
        <button type="button" onClick={createMock}><Play /> 启动 Mock 数据演示</button>
      </div>
      <label>
        <span>恢复已有 Live Session UUID</span>
        <div>
          <input value={sessionId} onChange={(event) => setSessionId(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") resume(); }} placeholder="粘贴 session UUID" />
          <button type="button" onClick={resume} disabled={!sessionId.trim()} aria-label="恢复会话"><ArrowRight /></button>
        </div>
      </label>
      <small><RotateCcw /> Mock 使用浏览器内临时引擎，完整刷新会重置；Live 才是持久化 YAML 验收路径。</small>
    </section>
  );
}
