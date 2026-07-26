"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useReducedMotion } from "framer-motion";

import {
  DEMO_WORLD_HEIGHT,
  DEMO_WORLD_WIDTH,
  type DemoPoint,
  type DemoRoom,
} from "@/lib/demo-data";

import { createCameraState, updateCameraFrame } from "./camera";
import {
  collectForegroundFadeElements,
  FOREGROUND_FADE_INTERVAL,
  updateForegroundFade,
  type ForegroundFadeElement,
} from "./fade";
import {
  clamp,
  collides,
  demoSeats,
  distance,
  findRoom,
  INTERACT_DISTANCE,
  MOVE_SPEED,
  PLAYER_RADIUS,
  SEAT_INTERACT_DISTANCE,
  sceneZ,
  UI_SNAPSHOT_INTERVAL,
} from "./geometry";
import type { LocalScenePose, WorldHotspot } from "./types";

const MOVEMENT_CODES = new Set([
  "KeyW", "KeyA", "KeyS", "KeyD",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
]);

function isInteractiveTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest("button, a, input, textarea, select, [contenteditable='true']"));
}

export interface MansionEngineOptions {
  initialPosition: DemoPoint;
  initialFacing: "left" | "right";
  /** 外部弹层打开或会话禁止交互时置 true：清空输入并冻结移动 */
  blocked: boolean;
  worldHotspots: WorldHotspot[];
  /** 引擎已确认该热点处于激活距离内，由调用方决定打开文章还是发起调查 */
  onInteractHotspot: (hotspot: WorldHotspot) => void;
  /** 每次移动输入（按键/触控）时回调一次，用于隐藏首屏操作提示 */
  onMoveInput?: () => void;
  onPlayerPose?: (pose: LocalScenePose) => void;
}

/**
 * 场景引擎：玩家移动、碰撞、相机跟随、交互判定与主循环。
 *
 * 渲染策略——高频坐标与相机状态绕过 React，直接写目标元素的 style；
 * 朝向和移动状态只在转换时更新，UI 坐标快照节流 250ms。主循环在玩家静止
 * 且相机收敛后自动休眠，由 wakeLoop 在任何输入/状态变化时唤醒。
 */
export function useMansionEngine({
  initialPosition,
  initialFacing,
  blocked,
  worldHotspots,
  onInteractHotspot,
  onMoveInput,
  onPlayerPose,
}: MansionEngineOptions) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const cameraElementRef = useRef<HTMLDivElement>(null);
  const playerElementRef = useRef<HTMLDivElement>(null);

  const keysRef = useRef(new Set<string>());
  const touchRef = useRef({ x: 0, y: 0 });
  const playerRef = useRef<DemoPoint>({ x: initialPosition.x, y: initialPosition.y });
  const viewportSizeRef = useRef({ width: 1280, height: 720 });
  const blockedRef = useRef(false);
  const activeHotspotRef = useRef<string | null>(null);
  const activeSeatRef = useRef<string | null>(null);
  const seatedChairRef = useRef<string | null>(null);
  const wakeLoopRef = useRef<() => void>(() => undefined);
  const reducedMotionRef = useRef(false);
  const lastSnapshotRef = useRef(0);
  const lastPoseEmissionRef = useRef(0);
  const cameraNeedsUpdateRef = useRef(true);
  const playerRenderDirtyRef = useRef(true);
  const interactionTargetsDirtyRef = useRef(true);
  const poseDirtyRef = useRef(true);
  const cameraRef = useRef(createCameraState(initialPosition));
  const foregroundFadeElementsRef = useRef<ForegroundFadeElement[]>([]);
  const worldHotspotsRef = useRef(worldHotspots);
  const onInteractHotspotRef = useRef(onInteractHotspot);
  const onMoveInputRef = useRef(onMoveInput);
  const onPlayerPoseRef = useRef(onPlayerPose);

  const shouldReduceMotion = useReducedMotion();
  const [playerSnapshot, setPlayerSnapshot] = useState(playerRef.current);
  const [playerFacing, setPlayerFacing] = useState<"left" | "right">(initialFacing);
  const [playerMoving, setPlayerMoving] = useState(false);
  const [activeHotspotId, setActiveHotspotId] = useState<string | null>(null);
  const [activeSeatId, setActiveSeatId] = useState<string | null>(null);
  const [seatedChairId, setSeatedChairId] = useState<string | null>(null);
  const [activeRoomId, setActiveRoomId] = useState<DemoRoom["id"]>("hall");

  useLayoutEffect(() => {
    onInteractHotspotRef.current = onInteractHotspot;
    onMoveInputRef.current = onMoveInput;
    onPlayerPoseRef.current = onPlayerPose;
  }, [onInteractHotspot, onMoveInput, onPlayerPose]);

  useLayoutEffect(() => {
    setPlayerFacing(initialFacing);
  }, [initialFacing]);

  useEffect(() => {
    worldHotspotsRef.current = worldHotspots;
    interactionTargetsDirtyRef.current = true;
    wakeLoopRef.current();
  }, [worldHotspots]);

  useEffect(() => {
    reducedMotionRef.current = Boolean(shouldReduceMotion);
  }, [shouldReduceMotion]);

  const clearInput = useCallback(() => {
    keysRef.current.clear();
    touchRef.current = { x: 0, y: 0 };
  }, []);

  useEffect(() => {
    blockedRef.current = blocked;
    if (blocked) clearInput();
    wakeLoopRef.current();
  }, [blocked, clearInput]);

  const movePlayerTo = useCallback((position: DemoPoint) => {
    playerRef.current = { ...position };
    setPlayerSnapshot({ ...position });
    updateForegroundFade(foregroundFadeElementsRef.current, position);
    cameraNeedsUpdateRef.current = true;
    playerRenderDirtyRef.current = true;
    interactionTargetsDirtyRef.current = true;
    poseDirtyRef.current = true;
    wakeLoopRef.current();
  }, []);

  const standUp = useCallback(() => {
    const chairId = seatedChairRef.current;
    if (!chairId) return;
    const chair = demoSeats.find((seat) => seat.id === chairId);
    seatedChairRef.current = null;
    setSeatedChairId(null);
    if (chair) movePlayerTo(chair.seat.stand);
  }, [movePlayerTo]);

  const sitDown = useCallback((chairId: string) => {
    const chair = demoSeats.find((seat) => seat.id === chairId);
    if (!chair) return;
    clearInput();
    activeSeatRef.current = null;
    activeHotspotRef.current = null;
    setActiveSeatId(null);
    setActiveHotspotId(null);
    seatedChairRef.current = chair.id;
    setSeatedChairId(chair.id);
    movePlayerTo(chair.seat.position);
  }, [clearInput, movePlayerTo]);

  const interactHotspot = useCallback((hotspot: WorldHotspot) => {
    if (activeHotspotRef.current !== hotspot.id) return;
    onInteractHotspotRef.current(hotspot);
  }, []);

  /** E/Enter 交互优先级：起身 > 坐下 > 热点 */
  const interact = useCallback(() => {
    if (seatedChairRef.current) {
      standUp();
      return;
    }
    const chairId = activeSeatRef.current;
    if (chairId) {
      sitDown(chairId);
      return;
    }
    const hotspotId = activeHotspotRef.current;
    if (!hotspotId) return;
    const hotspot = worldHotspotsRef.current.find((item) => item.id === hotspotId);
    if (hotspot) interactHotspot(hotspot);
  }, [interactHotspot, sitDown, standUp]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      viewportSizeRef.current = {
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      };
      cameraNeedsUpdateRef.current = true;
      wakeLoopRef.current();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const root = viewportRef.current;
    if (!root) return;
    const elements = collectForegroundFadeElements(root);
    foregroundFadeElementsRef.current = elements;
    updateForegroundFade(elements, playerRef.current);
  }, [activeRoomId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isInteractiveTarget(event.target)) return;
      if (MOVEMENT_CODES.has(event.code)) {
        if (blockedRef.current) return;
        event.preventDefault();
        if (seatedChairRef.current) standUp();
        keysRef.current.add(event.code);
        onMoveInputRef.current?.();
        wakeLoopRef.current();
        return;
      }
      if (!blockedRef.current && (event.code === "KeyE" || event.code === "Enter")) {
        event.preventDefault();
        interact();
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      keysRef.current.delete(event.code);
      wakeLoopRef.current();
    };
    const onBlur = () => clearInput();
    const onVisibility = () => {
      if (document.hidden) clearInput();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInput();
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [clearInput, interact, standUp]);

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    let lastMoving = false;
    let lastSnapshotMoving = false;
    let lastEmittedMoving: boolean | null = null;
    let lastFacing: "left" | "right" = initialFacing;
    let lastFadeUpdate = 0;

    const loop = (now: number) => {
      frame = 0;
      // delta 上限 32ms：切后台再回来时不产生瞬移
      const delta = Math.min((now - last) / 1000, 0.032);
      last = now;
      const keys = keysRef.current;
      const movementBlocked = blockedRef.current || Boolean(seatedChairRef.current);
      let dx = movementBlocked ? 0 : touchRef.current.x;
      let dy = movementBlocked ? 0 : touchRef.current.y;
      if (!movementBlocked) {
        if (keys.has("KeyA") || keys.has("ArrowLeft")) dx -= 1;
        if (keys.has("KeyD") || keys.has("ArrowRight")) dx += 1;
        if (keys.has("KeyW") || keys.has("ArrowUp")) dy -= 1;
        if (keys.has("KeyS") || keys.has("ArrowDown")) dy += 1;
      }
      const magnitude = Math.hypot(dx, dy);
      const isMoving = magnitude > 0;
      if (isMoving) {
        dx /= magnitude;
        dy /= magnitude;
        if (Math.abs(dx) > 0.05) {
          const nextFacing = dx < 0 ? "left" : "right";
          if (nextFacing !== lastFacing) {
            lastFacing = nextFacing;
            setPlayerFacing(nextFacing);
          }
        }
        // X/Y 轴分开做碰撞，贴墙时另一轴仍可滑动
        const current = playerRef.current;
        const nextX = {
          x: clamp(current.x + dx * MOVE_SPEED * delta, PLAYER_RADIUS, DEMO_WORLD_WIDTH - PLAYER_RADIUS),
          y: current.y,
        };
        const afterX = collides(nextX) ? current : nextX;
        const nextY = {
          x: afterX.x,
          y: clamp(afterX.y + dy * MOVE_SPEED * delta, PLAYER_RADIUS, DEMO_WORLD_HEIGHT - PLAYER_RADIUS),
        };
        playerRef.current = collides(nextY) ? afterX : nextY;
      }

      const player = playerRef.current;
      const playerPositionChanged = isMoving || playerRenderDirtyRef.current;
      const playerElement = playerElementRef.current;
      if (playerElement) {
        if (isMoving !== lastMoving) {
          lastMoving = isMoving;
          setPlayerMoving(isMoving);
        }
        if (playerPositionChanged) {
          playerElement.style.transform = `translate3d(${player.x}px, ${player.y}px, 0) translate(-50%, -100%)`;
          playerElement.style.zIndex = String(sceneZ(player.y));
          playerRenderDirtyRef.current = false;
        }
      }

      // 最近热点与最近座位互斥：距离更近者获得 E 键
      if (playerPositionChanged || interactionTargetsDirtyRef.current) {
        let nearestHotspotId: string | null = null;
        let nearestHotspotDistance = Infinity;
        let nearestSeatId: string | null = null;
        let nearestSeatDistance = Infinity;
        if (!seatedChairRef.current) {
          for (const hotspot of worldHotspotsRef.current) {
            const currentDistance = distance(player, hotspot);
            if (currentDistance < nearestHotspotDistance) {
              nearestHotspotId = hotspot.id;
              nearestHotspotDistance = currentDistance;
            }
          }
          for (const chair of demoSeats) {
            const currentDistance = distance(player, chair.seat.stand);
            if (currentDistance < nearestSeatDistance) {
              nearestSeatId = chair.id;
              nearestSeatDistance = currentDistance;
            }
          }
        }
        if (nearestHotspotDistance > INTERACT_DISTANCE) nearestHotspotId = null;
        if (nearestSeatDistance > SEAT_INTERACT_DISTANCE) nearestSeatId = null;
        if (nearestSeatId && nearestSeatDistance <= nearestHotspotDistance) {
          nearestHotspotId = null;
        } else {
          nearestSeatId = null;
        }
        if (nearestHotspotId !== activeHotspotRef.current) {
          activeHotspotRef.current = nearestHotspotId;
          setActiveHotspotId(nearestHotspotId);
        }
        if (nearestSeatId !== activeSeatRef.current) {
          activeSeatRef.current = nearestSeatId;
          setActiveSeatId(nearestSeatId);
        }
        interactionTargetsDirtyRef.current = false;
      }

      let cameraAnimating = false;
      if (isMoving || cameraNeedsUpdateRef.current) {
        const camera = cameraRef.current;
        const room = findRoom(player, camera.roomId);
        if (room.id !== camera.roomId) {
          camera.roomId = room.id;
          setActiveRoomId(room.id);
        }
        const result = updateCameraFrame(camera, {
          delta,
          dx: isMoving ? dx : 0,
          dy: isMoving ? dy : 0,
          viewport: viewportSizeRef.current,
          player,
          room,
          seated: Boolean(seatedChairRef.current),
          reduceMotion: reducedMotionRef.current,
        });
        if (cameraElementRef.current) {
          cameraElementRef.current.style.transform = result.transform;
        }
        cameraAnimating = result.animating;
        cameraNeedsUpdateRef.current = cameraAnimating;
      }
      if (isMoving && now - lastFadeUpdate >= FOREGROUND_FADE_INTERVAL) {
        lastFadeUpdate = now;
        updateForegroundFade(foregroundFadeElementsRef.current, player);
      }
      const snapshotMovementChanged = isMoving !== lastSnapshotMoving;
      if (snapshotMovementChanged || (isMoving && now - lastSnapshotRef.current >= UI_SNAPSHOT_INTERVAL)) {
        lastSnapshotMoving = isMoving;
        lastSnapshotRef.current = now;
        setPlayerSnapshot({ ...player });
      }
      const movingStateChanged = isMoving !== lastEmittedMoving;
      if (onPlayerPoseRef.current && (
        poseDirtyRef.current
        || movingStateChanged
        || (isMoving && now - lastPoseEmissionRef.current >= UI_SNAPSHOT_INTERVAL)
      )) {
        lastPoseEmissionRef.current = now;
        lastEmittedMoving = isMoving;
        poseDirtyRef.current = false;
        onPlayerPoseRef.current({
          x: player.x,
          y: player.y,
          facing: lastFacing,
          moving: isMoving,
        });
      }
      if (isMoving || cameraAnimating) frame = requestAnimationFrame(loop);
    };

    wakeLoopRef.current = () => {
      if (frame) return;
      last = performance.now();
      frame = requestAnimationFrame(loop);
    };
    wakeLoopRef.current();
    return () => {
      wakeLoopRef.current = () => undefined;
      cancelAnimationFrame(frame);
    };
  }, [initialFacing]);

  const setTouchDirection = useCallback((event: ReactPointerEvent<HTMLButtonElement>, x: number, y: number) => {
    if (blockedRef.current) return;
    if (seatedChairRef.current) standUp();
    event.currentTarget.setPointerCapture(event.pointerId);
    touchRef.current = { x, y };
    onMoveInputRef.current?.();
    wakeLoopRef.current();
  }, [standUp]);

  const clearTouchDirection = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    touchRef.current = { x: 0, y: 0 };
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const resetTouchDirection = useCallback(() => {
    touchRef.current = { x: 0, y: 0 };
  }, []);

  return {
    viewportRef,
    cameraElementRef,
    playerElementRef,
    playerRef,
    playerSnapshot,
    playerFacing,
    playerMoving,
    activeRoomId,
    activeHotspotId,
    activeSeatId,
    seatedChairId,
    interact,
    interactHotspot,
    sitDown,
    standUp,
    setTouchDirection,
    clearTouchDirection,
    resetTouchDirection,
  };
}
