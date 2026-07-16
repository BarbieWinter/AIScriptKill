"use client";

import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "framer-motion";
import {
  BookOpen,
  ChevronRight,
  CircleHelp,
  Footprints,
  Gauge,
  Headphones,
  Map as MapIcon,
  Menu,
  Volume2,
  X,
} from "lucide-react";
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import { StoryArticlePanel } from "@/components/demo/StoryArticlePanel";
import {
  DEMO_WORLD_HEIGHT,
  DEMO_WORLD_WIDTH,
  demoArticles,
  demoCharacters,
  demoDoorFrames,
  demoFurniture,
  demoHotspots,
  demoRooms,
  demoWalls,
  type DemoArticle,
  type DemoCharacter,
  type DemoFurniture,
  type DemoHotspot,
  type DemoPoint,
  type DemoRect,
  type DemoRoom,
  type DemoSessionHotspot,
  type DemoWall,
} from "@/lib/demo-data";

const PLAYER_RADIUS = 17;
const MOVE_SPEED = 270;
const INTERACT_DISTANCE = 118;
const SCENE_Z_BASE = 1000;
const UI_SNAPSHOT_INTERVAL = 90;
const ROOM_HYSTERESIS = 30;
const MOVEMENT_CODES = new Set([
  "KeyW",
  "KeyA",
  "KeyS",
  "KeyD",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
]);

type WorldHotspot =
  | (DemoHotspot & { kind: "article" })
  | (DemoSessionHotspot & { kind: "session" });

export interface MansionDemoProps {
  sessionHotspots?: DemoSessionHotspot[];
  interactionBlocked?: boolean;
  interactionPending?: boolean;
  onInvestigate?: (sceneId: string, hotspotId: string) => void | Promise<void>;
  overlay?: ReactNode;
  stageName?: string;
  statusLabel?: string;
}

function hotspotActionLabel(hotspot: WorldHotspot) {
  return hotspot.kind === "article" ? "阅读" : "调查";
}

interface CameraState {
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

const collisions: DemoRect[] = [
  ...demoWalls,
  ...demoFurniture.flatMap((entity) => (entity.collision ? [entity.collision] : [])),
];

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function distance(a: DemoPoint, b: DemoPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function collides(position: DemoPoint) {
  return collisions.some(
    (rect) =>
      position.x + PLAYER_RADIUS > rect.x &&
      position.x - PLAYER_RADIUS < rect.x + rect.width &&
      position.y + PLAYER_RADIUS > rect.y &&
      position.y - PLAYER_RADIUS < rect.y + rect.height,
  );
}

function contains(rect: DemoRect, point: DemoPoint, padding = 0) {
  return (
    point.x >= rect.x - padding &&
    point.x <= rect.x + rect.width + padding &&
    point.y >= rect.y - padding &&
    point.y <= rect.y + rect.height + padding
  );
}

function sceneZ(sortY: number) {
  return SCENE_Z_BASE + Math.round(clamp(sortY, 0, DEMO_WORLD_HEIGHT));
}

function findRoom(point: DemoPoint, previousId?: DemoRoom["id"]) {
  const previous = demoRooms.find((room) => room.id === previousId);
  if (previous && contains(previous.bounds, point, ROOM_HYSTERESIS)) return previous;
  return (
    demoRooms
      .filter((room) => contains(room.bounds, point))
      .sort((a, b) => b.priority - a.priority)[0] ?? demoRooms[1]
  );
}

function isInteractiveTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest("button, a, input, textarea, select, [contenteditable='true']"));
}

function characterStyle(character: DemoCharacter, position = character): CSSProperties {
  return {
    "--character-width": `${character.silhouette.width}px`,
    "--character-height": `${character.silhouette.height}px`,
    "--torso-height": `${character.silhouette.torsoHeight}px`,
    "--head-width": `${character.silhouette.headWidth}px`,
    "--head-height": `${character.silhouette.headHeight}px`,
    "--shoulder-radius": `${character.silhouette.shoulderRadius}%`,
    "--coat": character.palette.coat,
    "--trousers": character.palette.trousers,
    "--skin": character.palette.skin,
    "--hair": character.palette.hair,
    "--character-accent": character.palette.accent,
    "--idle-duration": `${character.motion.idleSeconds}s`,
    "--walk-duration": `${character.motion.walkSeconds}s`,
    "--motion-delay": `${character.motion.delaySeconds}s`,
    transform: `translate3d(${position.x}px, ${position.y}px, 0) translate(-50%, -100%)`,
    zIndex: sceneZ(position.y),
  } as CSSProperties;
}

interface CharacterSpriteProps {
  character: DemoCharacter;
  player?: boolean;
  elementRef?: React.RefObject<HTMLDivElement | null>;
  moving?: boolean;
  facing?: "left" | "right";
}

const CharacterSprite = memo(function CharacterSprite({
  character,
  player = false,
  elementRef,
  moving = false,
  facing = character.initialFacing,
}: CharacterSpriteProps) {
  return (
    <div
      ref={elementRef}
      className={`demo-character ${player ? "demo-character-player" : "demo-character-npc"} ${moving ? "is-moving" : ""} is-facing-${facing}`}
      data-character-id={character.id}
      data-outfit={character.outfit}
      data-accessory={character.accessory}
      style={characterStyle(character)}
    >
      <span className="demo-character-selection" />
      <span className="demo-character-shadow" />
      <span className="demo-character-facing">
        <span className="demo-character-rig">
          <span className="demo-character-head">
            <span className="demo-character-hair" />
            <span className="demo-character-face" />
          </span>
          <span className="demo-character-torso" />
          <span className="demo-character-arm demo-character-arm-left" />
          <span className="demo-character-arm demo-character-arm-right" />
          <span className="demo-character-leg demo-character-leg-left"><i /></span>
          <span className="demo-character-leg demo-character-leg-right"><i /></span>
          <span className="demo-character-accessory" />
        </span>
      </span>
      <span className="demo-character-name">{character.name}{player ? " · 你" : ""}</span>
    </div>
  );
});

function wallSlices(wall: DemoWall) {
  if (wall.axis === "horizontal") return [{ ...wall, sliceId: wall.id }];
  const sliceSize = 48;
  const count = Math.ceil(wall.height / sliceSize);
  return Array.from({ length: count }, (_, index) => ({
    ...wall,
    y: wall.y + index * sliceSize,
    height: Math.min(sliceSize, wall.height - index * sliceSize),
    sliceId: `${wall.id}-${index}`,
  }));
}

const StaticScene = memo(function StaticScene({
  activeHotspotId,
  hotspots,
  interactionPending,
  onInteract,
}: {
  activeHotspotId: string | null;
  hotspots: WorldHotspot[];
  interactionPending: boolean;
  onInteract: (hotspot: WorldHotspot) => void;
}) {
  return (
    <>
      <div className="demo-floor-layer">
        <div className="demo-floor" />
        <div className="demo-stage-glow" />
        <div className="demo-window-light demo-window-light-one" />
        <div className="demo-window-light demo-window-light-two" />
        <div className="demo-carpet" />
        <div className="demo-stage-door-recess"><span /></div>
        {demoRooms.map((room) => (
          <span key={room.id} className="demo-room-label" style={{ left: room.label.x, top: room.label.y }}>
            {room.name}
          </span>
        ))}
      </div>

      <div className="demo-shadow-layer" aria-hidden="true">
        {demoWalls.map((wall) => (
          <span
            key={wall.id}
            className="demo-ground-shadow demo-wall-shadow"
            style={{ left: wall.x + 7, top: wall.y + wall.height - 2, width: wall.width, height: 22 }}
          />
        ))}
        {demoFurniture.map((entity) => (
          <span
            key={entity.id}
            className="demo-ground-shadow demo-furniture-shadow"
            style={{ left: entity.x + 9, top: entity.y + entity.height - 4, width: entity.width, height: 24 }}
          />
        ))}
      </div>

      <div className="demo-depth-layer">
        {demoWalls.flatMap(wallSlices).map((wall) => (
          <div
            key={wall.sliceId}
            className="demo-wall-volume"
            data-wall-axis={wall.axis}
            data-fade-id={wall.fadeDistance ? wall.id : undefined}
            data-fade-distance={wall.fadeDistance}
            style={{
              left: wall.x,
              top: wall.y,
              width: wall.width,
              height: wall.height,
              "--wall-elevation": `${wall.elevation}px`,
              zIndex: sceneZ(wall.y + wall.height),
            } as CSSProperties}
          >
            <span className="demo-elevated-faces">
              <span className="demo-wall-front" />
              <span className="demo-wall-cap" />
              <span className="demo-wall-side" />
            </span>
          </div>
        ))}

        {demoDoorFrames.map((door) => {
          const horizontal = door.orientation === "horizontal";
          return (
            <div
              key={door.id}
              className="demo-door-frame"
              data-orientation={door.orientation}
              style={{
                left: door.x,
                top: door.y,
                width: door.width,
                height: door.height,
                zIndex: sceneZ(horizontal ? door.y + door.height : door.y + door.height / 2),
              }}
            >
              <span className="demo-door-jamb demo-door-jamb-a" />
              <span className="demo-door-jamb demo-door-jamb-b" />
              <span className="demo-door-lintel" />
            </div>
          );
        })}

        {demoFurniture.map((entity) => (
          <Furniture key={entity.id} entity={entity} />
        ))}

        {hotspots.map((hotspot) => (
          <button
            type="button"
            key={hotspot.id}
            className={`demo-hotspot ${hotspot.kind === "session" ? "is-session" : ""} ${activeHotspotId === hotspot.id ? "is-active" : ""}`}
            style={{ left: hotspot.x, top: hotspot.y, zIndex: sceneZ(hotspot.y) }}
            onClick={() => onInteract(hotspot)}
            disabled={interactionPending || activeHotspotId !== hotspot.id}
            aria-label={`${hotspotActionLabel(hotspot)}${hotspot.label}`}
          >
            <span className="demo-hotspot-ring" />
            <span className="demo-hotspot-core"><BookOpen aria-hidden="true" /></span>
            <span className="demo-hotspot-label">{hotspot.label}</span>
          </button>
        ))}

        {demoCharacters.slice(1).map((character) => (
          <CharacterSprite key={character.id} character={character} />
        ))}
      </div>
    </>
  );
});

function Furniture({ entity }: { entity: DemoFurniture }) {
  return (
    <div
      className="demo-furniture"
      data-kind={entity.kind}
      data-variant={entity.variant}
      data-fade-id={entity.fadeDistance ? entity.id : undefined}
      data-fade-distance={entity.fadeDistance}
      style={{
        left: entity.x,
        top: entity.y,
        width: entity.width,
        height: entity.height,
        rotate: entity.rotation ? `${entity.rotation}deg` : undefined,
        "--furniture-elevation": `${entity.elevation}px`,
        zIndex: sceneZ(entity.sortY),
      } as CSSProperties}
    >
      <span className="demo-elevated-faces">
        <span className="demo-furniture-body" />
        <span className="demo-furniture-top" />
        <span className="demo-furniture-front" />
        <span className="demo-furniture-detail" />
      </span>
    </div>
  );
}

export function MansionDemo({
  sessionHotspots = [],
  interactionBlocked = false,
  interactionPending = false,
  onInvestigate,
  overlay,
  stageName,
  statusLabel,
}: MansionDemoProps = {}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const cameraElementRef = useRef<HTMLDivElement>(null);
  const playerElementRef = useRef<HTMLDivElement>(null);
  const keysRef = useRef(new Set<string>());
  const touchRef = useRef({ x: 0, y: 0 });
  const playerRef = useRef<DemoPoint>({ x: demoCharacters[0].x, y: demoCharacters[0].y });
  const viewportSizeRef = useRef({ width: 1280, height: 720 });
  const blockedRef = useRef(false);
  const activeHotspotRef = useRef<string | null>(null);
  const reducedMotionRef = useRef(false);
  const lastSnapshotRef = useRef(0);
  const cameraRef = useRef<CameraState>({
    x: demoCharacters[0].x,
    y: demoCharacters[0].y,
    zoom: 1,
    targetX: demoCharacters[0].x,
    targetY: demoCharacters[0].y,
    targetZoom: 1,
    lookX: 0,
    lookY: 0,
    roomId: "south",
    initialized: false,
  });

  const shouldReduceMotion = useReducedMotion();
  const [playerSnapshot, setPlayerSnapshot] = useState(playerRef.current);
  const [facing, setFacing] = useState<"left" | "right">(demoCharacters[0].initialFacing);
  const [moving, setMoving] = useState(false);
  const [activeHotspotId, setActiveHotspotId] = useState<string | null>(null);
  const [activeRoomId, setActiveRoomId] = useState<DemoRoom["id"]>("south");
  const [selectedArticle, setSelectedArticle] = useState<DemoArticle | null>(null);
  const [showJournal, setShowJournal] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [showHelp, setShowHelp] = useState(true);
  const [muted, setMuted] = useState(false);

  const worldHotspots = useMemo<WorldHotspot[]>(
    () => [
      ...demoHotspots.map((hotspot) => ({ ...hotspot, kind: "article" as const })),
      ...sessionHotspots.map((hotspot) => ({ ...hotspot, kind: "session" as const })),
    ],
    [sessionHotspots],
  );
  const worldHotspotsRef = useRef(worldHotspots);

  useEffect(() => {
    worldHotspotsRef.current = worldHotspots;
  }, [worldHotspots]);

  const articleById = useMemo(
    () => new Map(demoArticles.map((article) => [article.id, article])),
    [],
  );

  const clearInput = useCallback(() => {
    keysRef.current.clear();
    touchRef.current = { x: 0, y: 0 };
  }, []);

  const openArticle = useCallback((articleId: string) => {
    const article = articleById.get(articleId);
    if (article) setSelectedArticle(article);
  }, [articleById]);

  const interactWithHotspot = useCallback((hotspot: WorldHotspot) => {
    if (interactionPending || activeHotspotRef.current !== hotspot.id) return;
    if (hotspot.kind === "article") {
      openArticle(hotspot.articleId);
      return;
    }
    void onInvestigate?.(hotspot.sceneId, hotspot.id);
  }, [interactionPending, onInvestigate, openArticle]);

  const interact = useCallback(() => {
    const hotspotId = activeHotspotRef.current;
    if (!hotspotId) return;
    const hotspot = worldHotspotsRef.current.find((item) => item.id === hotspotId);
    if (hotspot) interactWithHotspot(hotspot);
  }, [interactWithHotspot]);

  useEffect(() => {
    reducedMotionRef.current = Boolean(shouldReduceMotion);
  }, [shouldReduceMotion]);

  useEffect(() => {
    const blocked = interactionBlocked || selectedArticle !== null || showJournal || showMap;
    blockedRef.current = blocked;
    if (blocked) clearInput();
  }, [clearInput, interactionBlocked, selectedArticle, showJournal, showMap]);

  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      viewportSizeRef.current = {
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      };
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isInteractiveTarget(event.target)) return;
      if (MOVEMENT_CODES.has(event.code)) {
        if (blockedRef.current) return;
        event.preventDefault();
        keysRef.current.add(event.code);
        setShowHelp(false);
        return;
      }
      if (!blockedRef.current && (event.code === "KeyE" || event.code === "Enter")) {
        event.preventDefault();
        interact();
      }
      if (event.code === "Escape") {
        setSelectedArticle(null);
        setShowJournal(false);
        setShowMap(false);
      }
    };
    const onKeyUp = (event: KeyboardEvent) => keysRef.current.delete(event.code);
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
  }, [clearInput, interact]);

  useEffect(() => {
    let frame = 0;
    let last = performance.now();
    let lastMoving = false;
    let lastFacing: "left" | "right" = demoCharacters[0].initialFacing;
    let lastFadeUpdate = 0;

    const updateCamera = (delta: number, dx: number, dy: number) => {
      const camera = cameraRef.current;
      const viewport = viewportSizeRef.current;
      const player = playerRef.current;
      const room = findRoom(player, camera.roomId);
      if (room.id !== camera.roomId) {
        camera.roomId = room.id;
        setActiveRoomId(room.id);
      }

      const portrait = viewport.height > viewport.width * 1.15;
      const compact = viewport.width < 900;
      const maxVisibleWidth = portrait ? 520 : compact ? 760 : 1040;
      const maxVisibleHeight = portrait ? 700 : compact ? 500 : 650;
      const detailZoom = Math.max(viewport.width / maxVisibleWidth, viewport.height / maxVisibleHeight);
      const coverZoom = Math.max(viewport.width / DEMO_WORLD_WIDTH, viewport.height / DEMO_WORLD_HEIGHT);
      const roomFitZoom = Math.min(
        viewport.width / (room.bounds.width + room.camera.padding * 2),
        viewport.height / (room.bounds.height + room.camera.padding * 2),
      );
      camera.targetZoom = Math.max(
        coverZoom,
        detailZoom,
        Math.min(roomFitZoom * room.camera.zoomBias, detailZoom * 1.28),
      );

      const reduceMotion = reducedMotionRef.current;
      const lookAlpha = reduceMotion ? 1 : 1 - Math.exp(-4.8 * delta);
      const desiredLookX = reduceMotion ? 0 : dx * room.camera.lookAheadX;
      const desiredLookY = reduceMotion ? 0 : dy * room.camera.lookAheadY;
      camera.lookX += (desiredLookX - camera.lookX) * lookAlpha;
      camera.lookY += (desiredLookY - camera.lookY) * lookAlpha;

      let subjectX = player.x + camera.lookX;
      let subjectY = player.y + camera.lookY;
      if (room.camera.focus) {
        subjectX += (room.camera.focus.x - player.x) * room.camera.focusWeight;
        subjectY += (room.camera.focus.y - player.y) * room.camera.focusWeight;
      }

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

      const anchorX = viewport.width * (portrait ? 0.58 : 0.5);
      const anchorY = viewport.height * (portrait ? 0.43 : 0.5);
      const minX = anchorX / camera.targetZoom;
      const maxX = DEMO_WORLD_WIDTH - (viewport.width - anchorX) / camera.targetZoom;
      const minY = anchorY / camera.targetZoom;
      const maxY = DEMO_WORLD_HEIGHT - (viewport.height - anchorY) / camera.targetZoom;
      camera.targetX = minX > maxX ? DEMO_WORLD_WIDTH / 2 : clamp(camera.targetX, minX, maxX);
      camera.targetY = minY > maxY ? DEMO_WORLD_HEIGHT / 2 : clamp(camera.targetY, minY, maxY);

      const positionAlpha = reduceMotion ? 1 : 1 - Math.exp(-7.2 * delta);
      const zoomAlpha = reduceMotion ? 1 : 1 - Math.exp(-5.2 * delta);
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
      if (cameraElementRef.current) {
        cameraElementRef.current.style.transform = `translate3d(${translateX}px, ${translateY}px, 0) scale(${camera.zoom})`;
      }
    };

    const updateForegroundFade = (now: number) => {
      if (now - lastFadeUpdate < 80) return;
      lastFadeUpdate = now;
      const player = playerRef.current;
      document.querySelectorAll<HTMLElement>("[data-fade-id]").forEach((element) => {
        const distanceLimit = Number(element.dataset.fadeDistance || 0);
        const rectX = Number.parseFloat(element.style.left || "0");
        const rectY = Number.parseFloat(element.style.top || "0");
        const width = Number.parseFloat(element.style.width || "0");
        const height = Number.parseFloat(element.style.height || "0");
        const closestX = clamp(player.x, rectX, rectX + width);
        const closestY = clamp(player.y, rectY, rectY + height);
        const behind = player.y <= rectY + height;
        element.classList.toggle(
          "is-player-behind",
          behind && Math.hypot(player.x - closestX, player.y - closestY) < distanceLimit,
        );
      });
    };

    const loop = (now: number) => {
      const delta = Math.min((now - last) / 1000, 0.032);
      last = now;
      const keys = keysRef.current;
      let dx = blockedRef.current ? 0 : touchRef.current.x;
      let dy = blockedRef.current ? 0 : touchRef.current.y;
      if (!blockedRef.current) {
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
        if (Math.abs(dx) > 0.05) lastFacing = dx < 0 ? "left" : "right";
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

      if (isMoving !== lastMoving) {
        lastMoving = isMoving;
        setMoving(isMoving);
      }
      setFacing((current) => (current === lastFacing ? current : lastFacing));

      const player = playerRef.current;
      const playerElement = playerElementRef.current;
      if (playerElement) {
        playerElement.style.transform = `translate3d(${player.x}px, ${player.y}px, 0) translate(-50%, -100%)`;
        playerElement.style.zIndex = String(sceneZ(player.y));
      }

      let nearestId: string | null = null;
      let nearestDistance = Infinity;
      for (const hotspot of worldHotspotsRef.current) {
        const currentDistance = distance(player, hotspot);
        if (currentDistance < nearestDistance) {
          nearestId = hotspot.id;
          nearestDistance = currentDistance;
        }
      }
      if (nearestDistance > INTERACT_DISTANCE) nearestId = null;
      if (nearestId !== activeHotspotRef.current) {
        activeHotspotRef.current = nearestId;
        setActiveHotspotId(nearestId);
      }

      updateCamera(delta, isMoving ? dx : 0, isMoving ? dy : 0);
      updateForegroundFade(now);
      if (now - lastSnapshotRef.current >= UI_SNAPSHOT_INTERVAL) {
        lastSnapshotRef.current = now;
        setPlayerSnapshot({ ...player });
      }
      frame = requestAnimationFrame(loop);
    };

    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, []);

  const nearestHotspot = activeHotspotId
    ? worldHotspots.find((hotspot) => hotspot.id === activeHotspotId) ?? null
    : null;
  const activeRoom = demoRooms.find((room) => room.id === activeRoomId) ?? demoRooms[1];

  const setTouchDirection = (event: ReactPointerEvent<HTMLButtonElement>, x: number, y: number) => {
    if (blockedRef.current) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    touchRef.current = { x, y };
    setShowHelp(false);
  };

  const clearTouchDirection = (event: ReactPointerEvent<HTMLButtonElement>) => {
    touchRef.current = { x: 0, y: 0 };
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <MotionConfig reducedMotion="user">
      <main className="mansion-demo" ref={viewportRef} data-room={activeRoomId}>
        <div ref={cameraElementRef} className="demo-world-camera">
          <div className="demo-world" style={{ width: DEMO_WORLD_WIDTH, height: DEMO_WORLD_HEIGHT }}>
            <StaticScene
              activeHotspotId={activeHotspotId}
              hotspots={worldHotspots}
              interactionPending={interactionPending}
              onInteract={interactWithHotspot}
            />
            <CharacterSprite
              character={demoCharacters[0]}
              player
              elementRef={playerElementRef}
              moving={moving}
              facing={facing}
            />
          </div>
        </div>

        <div className="demo-vignette" />
        <div className="demo-film-grain" />
        <div className="demo-dust" aria-hidden="true" />

        <header className="demo-hud-top">
          <div className="demo-location-card">
            <span className="demo-location-index">01</span>
            <div><p>旧剧场 · {activeRoom.name}</p><span>{stageName ?? "前端视觉与操作原型"}</span></div>
          </div>
          <nav className="demo-hud-actions" aria-label="游戏界面操作">
            <button type="button" onClick={() => setShowMap(true)}><MapIcon /><span>地图</span></button>
            <button type="button" onClick={() => setShowJournal(true)}><BookOpen /><span>手记</span></button>
            <button type="button" onClick={() => setMuted((value) => !value)}>{muted ? <X /> : <Volume2 />}<span>{muted ? "静音" : "环境音"}</span></button>
            <button type="button" onClick={() => setShowHelp((value) => !value)}><Menu /><span>操作</span></button>
          </nav>
        </header>

        <aside className="demo-objective-card">
          <span>{stageName ? `当前阶段 · ${stageName}` : `探索模式 · ${activeRoom.name}`}</span>
          <p>{stageName ? "在精致地图中靠近发光热点，调查 YAML 剧本当前允许的内容。" : "在旧剧场中自由行走，靠近发光标记阅读静态剧情组件。"}</p>
          <div><Footprints /> WASD / 方向键移动</div>
        </aside>

        <AnimatePresence>
          {nearestHotspot && !selectedArticle && !interactionBlocked && (
            <motion.button
              type="button"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="demo-interact-prompt"
              onClick={interact}
              disabled={interactionPending}
            >
              <kbd>E</kbd><span>{interactionPending ? "处理中" : hotspotActionLabel(nearestHotspot)}</span><strong>{nearestHotspot.label}</strong>
            </motion.button>
          )}
        </AnimatePresence>

        <div className="demo-status-bar">
          <span><Gauge /> {statusLabel ?? "视觉原型 · 本地运行"}</span>
          <span className="demo-status-separator" />
          <span><Headphones /> 建议佩戴耳机</span>
          <span className="demo-status-coordinate">X {Math.round(playerSnapshot.x)} · Y {Math.round(playerSnapshot.y)}</span>
        </div>

        {overlay}

        <AnimatePresence>
          {showHelp && (
            <motion.div className="demo-help-card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 14 }}>
              <CircleHelp />
              <div><strong>先感受移动与尺度</strong><span>使用 WASD / 方向键行走，靠近光点按 E 阅读。</span></div>
              <button type="button" onClick={() => setShowHelp(false)}>知道了</button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="demo-touch-pad" aria-label="触控方向键">
          {[
            { label: "向上", symbol: "↑", x: 0, y: -1 },
            { label: "向左", symbol: "←", x: -1, y: 0 },
            { label: "向下", symbol: "↓", x: 0, y: 1 },
            { label: "向右", symbol: "→", x: 1, y: 0 },
          ].map((direction) => (
            <button
              key={direction.label}
              type="button"
              aria-label={direction.label}
              onPointerDown={(event) => setTouchDirection(event, direction.x, direction.y)}
              onPointerUp={clearTouchDirection}
              onPointerCancel={clearTouchDirection}
              onLostPointerCapture={() => { touchRef.current = { x: 0, y: 0 }; }}
            >
              {direction.symbol}
            </button>
          ))}
        </div>

        <AnimatePresence>
          {selectedArticle && <StoryArticlePanel article={selectedArticle} onClose={() => setSelectedArticle(null)} />}
        </AnimatePresence>

        <AnimatePresence>
          {showJournal && (
            <motion.div className="demo-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setShowJournal(false)}>
              <motion.section className="demo-journal" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} onClick={(event) => event.stopPropagation()}>
                <header><div><span>静态数据组件</span><h2>已发现的手记</h2></div><button type="button" onClick={() => setShowJournal(false)}><X /></button></header>
                <div className="demo-journal-list">
                  {demoArticles.map((article, index) => (
                    <button type="button" key={article.id} onClick={() => { setShowJournal(false); setSelectedArticle(article); }}>
                      <span>0{index + 1}</span><div><strong>{article.title}</strong><p>{article.summary}</p></div><ChevronRight />
                    </button>
                  ))}
                </div>
              </motion.section>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {showMap && (
            <motion.div className="demo-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setShowMap(false)}>
              <motion.section className="demo-map-panel" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} onClick={(event) => event.stopPropagation()}>
                <header><div><span>区域概览</span><h2>旧剧场一层</h2></div><button type="button" onClick={() => setShowMap(false)}><X /></button></header>
                <div className="demo-mini-map">
                  {demoRooms.map((room) => (
                    <div
                      key={room.id}
                      className="mini-room"
                      style={{
                        left: `${(room.bounds.x / DEMO_WORLD_WIDTH) * 100}%`,
                        top: `${(room.bounds.y / DEMO_WORLD_HEIGHT) * 100}%`,
                        width: `${(room.bounds.width / DEMO_WORLD_WIDTH) * 100}%`,
                        height: `${(room.bounds.height / DEMO_WORLD_HEIGHT) * 100}%`,
                      }}
                    >
                      {room.name.replace("西侧", "").replace("中央", "").replace("与幕间", "")}
                    </div>
                  ))}
                  <span style={{ left: `${(playerSnapshot.x / DEMO_WORLD_WIDTH) * 100}%`, top: `${(playerSnapshot.y / DEMO_WORLD_HEIGHT) * 100}%` }} />
                </div>
                <p>这是用于确认空间比例与操作方式的通用封闭舞台，不包含任务或后端状态。</p>
              </motion.section>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </MotionConfig>
  );
}
