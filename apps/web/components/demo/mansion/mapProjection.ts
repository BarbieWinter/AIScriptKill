import type { CSSProperties } from "react";

import {
  DEMO_WORLD_HEIGHT,
  DEMO_WORLD_WIDTH,
  type DemoPoint,
  type DemoRect,
} from "@/lib/demo-data";

export function pointToMapStyle(point: DemoPoint): CSSProperties {
  return {
    left: `${(point.x / DEMO_WORLD_WIDTH) * 100}%`,
    top: `${(point.y / DEMO_WORLD_HEIGHT) * 100}%`,
  };
}

export function rectToMapStyle(rect: DemoRect): CSSProperties {
  return {
    ...pointToMapStyle(rect),
    width: `${(rect.width / DEMO_WORLD_WIDTH) * 100}%`,
    height: `${(rect.height / DEMO_WORLD_HEIGHT) * 100}%`,
  };
}
