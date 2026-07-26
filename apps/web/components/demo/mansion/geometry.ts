import {
  DEMO_WORLD_HEIGHT,
  demoFurniture,
  demoRooms,
  demoWalls,
  type DemoFurniture,
  type DemoPoint,
  type DemoRect,
  type DemoRoom,
} from "@/lib/demo-data";

export const PLAYER_RADIUS = 17;
export const MOVE_SPEED = 270;
export const INTERACT_DISTANCE = 118;
export const SEAT_INTERACT_DISTANCE = 112;

/** 移动中同步 React 快照（坐标 HUD、小地图）与对外姿态广播的节流间隔 */
export const UI_SNAPSHOT_INTERVAL = 250;

/** 场景 z-index 统一为 1000 + 世界 Y：越靠画面下方的物体盖住越靠上方的 */
const SCENE_Z_BASE = 1000;

/** 房间判定迟滞：离开原房间边界 30px 内仍算原房间，站在门口时相机不会来回切换 */
const ROOM_HYSTERESIS = 30;

export type DemoSeat = DemoFurniture & {
  seat: NonNullable<DemoFurniture["seat"]>;
};

export const collisions: DemoRect[] = [
  ...demoWalls,
  ...demoFurniture.flatMap((entity) => (entity.collision ? [entity.collision] : [])),
];

export const demoSeats = demoFurniture.filter(
  (entity): entity is DemoSeat => Boolean(entity.seat),
);

export function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function distance(a: DemoPoint, b: DemoPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function collides(position: DemoPoint) {
  return collisions.some(
    (rect) =>
      position.x + PLAYER_RADIUS > rect.x &&
      position.x - PLAYER_RADIUS < rect.x + rect.width &&
      position.y + PLAYER_RADIUS > rect.y &&
      position.y - PLAYER_RADIUS < rect.y + rect.height,
  );
}

export function contains(rect: DemoRect, point: DemoPoint, padding = 0) {
  return (
    point.x >= rect.x - padding &&
    point.x <= rect.x + rect.width + padding &&
    point.y >= rect.y - padding &&
    point.y <= rect.y + rect.height + padding
  );
}

export function intersects(a: DemoRect, b: DemoRect) {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

export function sceneZ(sortY: number) {
  return SCENE_Z_BASE + Math.round(clamp(sortY, 0, DEMO_WORLD_HEIGHT));
}

export function findRoom(point: DemoPoint, previousId?: DemoRoom["id"]) {
  const previous = demoRooms.find((room) => room.id === previousId);
  if (previous && contains(previous.bounds, point, ROOM_HYSTERESIS)) return previous;
  return (
    demoRooms
      .filter((room) => contains(room.bounds, point))
      .sort((a, b) => b.priority - a.priority)[0]
      ?? demoRooms.find((room) => room.id === "hall")
      ?? demoRooms[0]
  );
}

/** 只渲染当前房间外扩一圈的静态物体，房间外的墙体家具直接不进 DOM */
export function sceneRenderBounds(roomId: DemoRoom["id"]): DemoRect {
  const room = demoRooms.find((candidate) => candidate.id === roomId) ?? demoRooms[0];
  const margin = room.id === "hall" ? 180 : 150;
  return {
    x: room.bounds.x - margin,
    y: room.bounds.y - margin,
    width: room.bounds.width + margin * 2,
    height: room.bounds.height + margin * 2,
  };
}
