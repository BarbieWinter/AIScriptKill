import type { DemoHotspot, DemoPoint, DemoSessionHotspot } from "@/lib/demo-data";

/** 场景热点：article 打开本地静态手记，session 触发后端调查指令 */
export type WorldHotspot =
  | (DemoHotspot & { kind: "article" })
  | (DemoSessionHotspot & { kind: "session" });

export interface SceneAvatar {
  id: string;
  characterId: string;
  name: string;
  x: number;
  y: number;
  facing: "left" | "right";
  moving?: boolean;
  online?: boolean;
}

export interface LocalScenePose extends DemoPoint {
  facing: "left" | "right";
  moving: boolean;
}
