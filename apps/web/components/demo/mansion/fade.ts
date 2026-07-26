import { demoFurniture, demoWalls, type DemoPoint, type DemoRect } from "@/lib/demo-data";

import { clamp } from "./geometry";

/** 前景淡出检测的节流间隔：人眼对遮挡切换不敏感，80ms 足够跟手 */
export const FOREGROUND_FADE_INTERVAL = 80;

/** 会挡住人物的前景体（声明了 fadeDistance 的墙与家具），按 id 预建矩形索引 */
const fadeTargets = new Map<string, { rect: DemoRect; fadeDistance: number }>(
  [...demoWalls, ...demoFurniture].flatMap((entity) =>
    entity.fadeDistance
      ? [[
          entity.id,
          {
            rect: { x: entity.x, y: entity.y, width: entity.width, height: entity.height },
            fadeDistance: entity.fadeDistance,
          },
        ] as const]
      : [],
  ),
);

export interface ForegroundFadeElement {
  element: HTMLElement;
  rect: DemoRect;
  fadeDistance: number;
}

/** 房间 DOM 更新后收集一次固定前景体，移动热路径不再反复查询 DOM */
export function collectForegroundFadeElements(root: HTMLElement): ForegroundFadeElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("[data-fade-id]")).flatMap((element) => {
    const target = fadeTargets.get(element.dataset.fadeId ?? "");
    return target ? [{ element, ...target }] : [];
  });
}

/** 玩家走到前景体背后且足够近时，为对应元素打上 is-player-behind 使其半透明 */
export function updateForegroundFade(elements: ForegroundFadeElement[], player: DemoPoint) {
  elements.forEach(({ element, rect, fadeDistance }) => {
    const closestX = clamp(player.x, rect.x, rect.x + rect.width);
    const closestY = clamp(player.y, rect.y, rect.y + rect.height);
    const behind = player.y <= rect.y + rect.height;
    element.classList.toggle(
      "is-player-behind",
      behind && Math.hypot(player.x - closestX, player.y - closestY) < fadeDistance,
    );
  });
}
