import {
  demoRooms,
  type DemoPoint,
  type DemoRoom,
  type DemoSessionHotspot,
} from "@/lib/demo-data";

interface PresentedHotspot {
  id: string;
  label: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
}

interface SceneLayout {
  roomId: DemoRoom["id"];
  spawn: DemoPoint;
  hotspotAnchors?: Record<string, DemoPoint>;
}

const sceneLayouts: Record<string, SceneLayout> = {
  "restaurant-hall": {
    roomId: "hall",
    spawn: { x: 1200, y: 1120 },
  },
  "back-alley": {
    roomId: "archive",
    spawn: { x: 2020, y: 1280 },
    hotspotAnchors: {
      "back-door-traces": { x: 2160, y: 1280 },
    },
  },
};

const safeNumber = (value: number, fallback: number) =>
  Number.isFinite(value) ? value : fallback;

export function sceneSpawn(sceneId: string): DemoPoint | null {
  return sceneLayouts[sceneId]?.spawn ?? null;
}

export function mapPresentationHotspots(
  sceneId: string,
  hotspots: PresentedHotspot[],
): DemoSessionHotspot[] {
  const layout = sceneLayouts[sceneId];
  if (!layout) return [];

  const room = demoRooms.find((candidate) => candidate.id === layout.roomId);
  if (!room) return [];

  const inset = 72;
  const usableWidth = Math.max(1, room.bounds.width - inset * 2);
  const usableHeight = Math.max(1, room.bounds.height - inset * 2);

  return hotspots.map((hotspot) => {
    const anchor = layout.hotspotAnchors?.[hotspot.id];
    const normalizedX = Math.min(100, Math.max(0, safeNumber(hotspot.x, 50))) / 100;
    const normalizedY = Math.min(100, Math.max(0, safeNumber(hotspot.y, 50))) / 100;

    return {
      id: hotspot.id,
      sceneId,
      label: hotspot.label,
      x: anchor?.x ?? room.bounds.x + inset + normalizedX * usableWidth,
      y: anchor?.y ?? room.bounds.y + inset + normalizedY * usableHeight,
      width: hotspot.width,
      height: hotspot.height,
    };
  });
}
