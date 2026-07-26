import {
  DEMO_WORLD_HEIGHT,
  DEMO_WORLD_WIDTH,
  type DemoPoint,
  type DemoRoom,
} from "@/lib/demo-data";

import { clamp } from "./geometry";

/** 坐下时相机推近圆桌的取景参数 */
const ROUND_TABLE_FOCUS = { x: 1200, y: 800 };
const ROUND_TABLE_VIEW = { width: 620, height: 560, maxZoom: 1.55 };

/**
 * 指数平滑系数（每帧 alpha = 1 - e^(-k·delta)），k 越大跟随越紧。
 * 位置(7.2)最紧、缩放(5.2)次之、移动前瞻(4.8)最松——三者节奏错开
 * 才有"镜头先稳住人、再缓缓调焦"的手感，调整前先进场景实走验证。
 */
const POSITION_SMOOTHING = 7.2;
const ZOOM_SMOOTHING = 5.2;
const LOOK_SMOOTHING = 4.8;

export interface CameraState {
  x: number;
  y: number;
  zoom: number;
  targetX: number;
  targetY: number;
  targetZoom: number;
  lookX: number;
  lookY: number;
  roomId: DemoRoom["id"];
  initialized: boolean;
}

export function createCameraState(origin: DemoPoint): CameraState {
  return {
    x: origin.x,
    y: origin.y,
    zoom: 1,
    targetX: origin.x,
    targetY: origin.y,
    targetZoom: 1,
    lookX: 0,
    lookY: 0,
    roomId: "hall",
    initialized: false,
  };
}

export interface CameraFrame {
  delta: number;
  /** 归一化移动方向，用于镜头前瞻；静止时传 0 */
  dx: number;
  dy: number;
  viewport: { width: number; height: number };
  player: DemoPoint;
  room: DemoRoom;
  seated: boolean;
  reduceMotion: boolean;
}

/**
 * 推进一帧相机状态。纯计算，不触碰 DOM；调用方把返回的 transform
 * 写到相机层元素上。animating 为 false 表示已收敛，主循环可以休眠。
 */
export function updateCameraFrame(
  camera: CameraState,
  frame: CameraFrame,
): { animating: boolean; transform: string } {
  const { delta, viewport, player, room, seated, reduceMotion } = frame;

  // 无论如何不能看到世界外：cover 缩放是所有取景模式的下限
  const coverZoom = Math.max(
    viewport.width / DEMO_WORLD_WIDTH,
    viewport.height / DEMO_WORLD_HEIGHT,
  );
  const portrait = viewport.height > viewport.width * 1.15;

  const lookAlpha = reduceMotion ? 1 : 1 - Math.exp(-LOOK_SMOOTHING * delta);
  const desiredLookX = seated || reduceMotion ? 0 : frame.dx * room.camera.lookAheadX;
  const desiredLookY = seated || reduceMotion ? 0 : frame.dy * room.camera.lookAheadY;
  camera.lookX += (desiredLookX - camera.lookX) * lookAlpha;
  camera.lookY += (desiredLookY - camera.lookY) * lookAlpha;

  if (seated) {
    const tableFitZoom = Math.min(
      viewport.width / ROUND_TABLE_VIEW.width,
      viewport.height / ROUND_TABLE_VIEW.height,
    );
    camera.targetZoom = Math.max(coverZoom, Math.min(tableFitZoom, ROUND_TABLE_VIEW.maxZoom));
    camera.targetX = ROUND_TABLE_FOCUS.x;
    camera.targetY = ROUND_TABLE_FOCUS.y;
  } else {
    // 可视范围上限（世界像素）随视口档位变化，保证小屏也能看清人物
    const compact = viewport.width < 900;
    const maxVisibleWidth = portrait ? 520 : compact ? 760 : 1040;
    const maxVisibleHeight = portrait ? 700 : compact ? 500 : 650;
    const detailZoom = Math.max(viewport.width / maxVisibleWidth, viewport.height / maxVisibleHeight);
    const roomFitZoom = Math.min(
      viewport.width / (room.bounds.width + room.camera.padding * 2),
      viewport.height / (room.bounds.height + room.camera.padding * 2),
    );
    camera.targetZoom = Math.max(
      coverZoom,
      detailZoom,
      Math.min(roomFitZoom * room.camera.zoomBias, detailZoom * 1.28),
    );

    let subjectX = player.x + camera.lookX;
    let subjectY = player.y + camera.lookY;
    if (room.camera.focus) {
      subjectX += (room.camera.focus.x - player.x) * room.camera.focusWeight;
      subjectY += (room.camera.focus.y - player.y) * room.camera.focusWeight;
    }

    // 死区跟随：人物在画面中央一块区域内自由移动，出界才拖动镜头
    const visibleWidth = viewport.width / camera.targetZoom;
    const visibleHeight = viewport.height / camera.targetZoom;
    const deadX = visibleWidth * (portrait ? 0.12 : 0.18);
    const deadY = visibleHeight * (portrait ? 0.13 : 0.16);
    if (!camera.initialized) {
      camera.targetX = subjectX;
      camera.targetY = subjectY;
    } else {
      if (subjectX < camera.targetX - deadX) camera.targetX = subjectX + deadX;
      if (subjectX > camera.targetX + deadX) camera.targetX = subjectX - deadX;
      if (subjectY < camera.targetY - deadY) camera.targetY = subjectY + deadY;
      if (subjectY > camera.targetY + deadY) camera.targetY = subjectY - deadY;
    }
  }

  // 视口锚点（竖屏时人物略偏上、偏右，给底部操作区留空间），并夹取到世界边界
  const anchorX = viewport.width * (seated ? 0.5 : portrait ? 0.58 : 0.5);
  const anchorY = viewport.height * (seated ? 0.5 : portrait ? 0.43 : 0.5);
  const minX = anchorX / camera.targetZoom;
  const maxX = DEMO_WORLD_WIDTH - (viewport.width - anchorX) / camera.targetZoom;
  const minY = anchorY / camera.targetZoom;
  const maxY = DEMO_WORLD_HEIGHT - (viewport.height - anchorY) / camera.targetZoom;
  camera.targetX = minX > maxX ? DEMO_WORLD_WIDTH / 2 : clamp(camera.targetX, minX, maxX);
  camera.targetY = minY > maxY ? DEMO_WORLD_HEIGHT / 2 : clamp(camera.targetY, minY, maxY);

  const positionAlpha = reduceMotion ? 1 : 1 - Math.exp(-POSITION_SMOOTHING * delta);
  const zoomAlpha = reduceMotion ? 1 : 1 - Math.exp(-ZOOM_SMOOTHING * delta);
  if (!camera.initialized) {
    camera.x = camera.targetX;
    camera.y = camera.targetY;
    camera.zoom = camera.targetZoom;
    camera.initialized = true;
  } else {
    camera.x += (camera.targetX - camera.x) * positionAlpha;
    camera.y += (camera.targetY - camera.y) * positionAlpha;
    camera.zoom += (camera.targetZoom - camera.zoom) * zoomAlpha;
  }

  const translateX = anchorX - camera.x * camera.zoom;
  const translateY = anchorY - camera.y * camera.zoom;
  const animating =
    Math.abs(camera.targetX - camera.x) > 0.2 ||
    Math.abs(camera.targetY - camera.y) > 0.2 ||
    Math.abs(camera.targetZoom - camera.zoom) > 0.001 ||
    Math.abs(camera.lookX) > 0.2 ||
    Math.abs(camera.lookY) > 0.2;

  return {
    animating,
    transform: `translate3d(${translateX}px, ${translateY}px, 0) scale(${camera.zoom})`,
  };
}
