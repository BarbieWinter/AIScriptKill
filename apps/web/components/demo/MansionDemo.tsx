"use client";

import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import {
  Armchair,
  BookOpen,
  CircleHelp,
  Footprints,
  Gauge,
  Headphones,
  Map as MapIcon,
  Menu,
  Volume2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { StoryArticlePanel } from "@/components/demo/StoryArticlePanel";
import {
  DEMO_WORLD_HEIGHT,
  DEMO_WORLD_WIDTH,
  demoArticles,
  demoCharacters,
  demoHotspots,
  demoRooms,
  type DemoArticle,
  type DemoPoint,
  type DemoSessionHotspot,
} from "@/lib/demo-data";

import {
  CharacterSprite,
  multiplayerAvatarTemplate,
  sceneCharacterForAvatar,
} from "./mansion/CharacterSprite";
import { demoSeats } from "./mansion/geometry";
import { SceneMiniMap } from "./mansion/SceneMiniMap";
import { JournalOverlay, MapOverlay } from "./mansion/SceneOverlays";
import { hotspotActionLabel, StaticScene } from "./mansion/StaticScene";
import type { LocalScenePose, SceneAvatar, WorldHotspot } from "./mansion/types";
import { useMansionEngine } from "./mansion/useMansionEngine";

export type { LocalScenePose, SceneAvatar } from "./mansion/types";

export interface MansionDemoProps {
  sessionHotspots?: DemoSessionHotspot[];
  interactionBlocked?: boolean;
  interactionPending?: boolean;
  onInvestigate?: (sceneId: string, hotspotId: string) => void | Promise<void>;
  overlay?: ReactNode;
  playerName?: string;
  playerCharacterId?: string;
  remoteAvatars?: SceneAvatar[];
  onPlayerPose?: (pose: LocalScenePose) => void;
  stageName?: string;
  statusLabel?: string;
  objectiveText?: string;
  /** false 时隐藏演示 NPC 与静态手记热点，只保留会话内容（多人模式用） */
  includeDemoContent?: boolean;
  journalLabel?: string;
  onOpenJournal?: () => void;
  initialPlayerPosition?: DemoPoint;
}

const TOUCH_DIRECTIONS = [
  { label: "向上", symbol: "↑", x: 0, y: -1 },
  { label: "向左", symbol: "←", x: -1, y: 0 },
  { label: "向下", symbol: "↓", x: 0, y: 1 },
  { label: "向右", symbol: "→", x: 1, y: 0 },
] as const;

const ARTICLE_BY_ID = new Map(demoArticles.map((article) => [article.id, article]));

/**
 * 可走动巨物舞台的编排层：拼装引擎（移动/相机/交互）、静态场景、
 * HUD 与弹层。运行细节见 mansion/useMansionEngine，取景逻辑见 mansion/camera。
 */
export function MansionDemo({
  sessionHotspots = [],
  interactionBlocked = false,
  interactionPending = false,
  onInvestigate,
  overlay,
  playerName,
  playerCharacterId,
  remoteAvatars = [],
  onPlayerPose,
  stageName,
  statusLabel,
  objectiveText,
  includeDemoContent = true,
  journalLabel = "手记",
  onOpenJournal,
  initialPlayerPosition,
}: MansionDemoProps = {}) {
  const [selectedArticle, setSelectedArticle] = useState<DemoArticle | null>(null);
  const [showJournal, setShowJournal] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [showHelp, setShowHelp] = useState(true);
  const [muted, setMuted] = useState(false);

  const initialPosition = initialPlayerPosition ?? demoCharacters[0];

  const sceneCharacters = useMemo(
    () => includeDemoContent
      ? demoCharacters.slice(1).map((character) => ({
          character,
          avatarCharacterId: character.id,
          moving: false,
          online: true,
        }))
      : remoteAvatars.map((avatar) => ({
          character: sceneCharacterForAvatar(avatar),
          avatarCharacterId: avatar.characterId,
          moving: Boolean(avatar.moving),
          online: avatar.online !== false,
        })),
    [includeDemoContent, remoteAvatars],
  );

  const worldHotspots = useMemo<WorldHotspot[]>(
    () => [
      ...(includeDemoContent
        ? demoHotspots.map((hotspot) => ({ ...hotspot, kind: "article" as const }))
        : []),
      ...sessionHotspots.map((hotspot) => ({ ...hotspot, kind: "session" as const })),
    ],
    [includeDemoContent, sessionHotspots],
  );

  const playerCharacter = useMemo(() => {
    const template = multiplayerAvatarTemplate(playerCharacterId ?? "");
    return {
      ...template,
      id: playerCharacterId ? `self-${playerCharacterId}` : template.id,
      name: playerName || template.name,
    };
  }, [playerCharacterId, playerName]);

  const interactWithHotspot = useCallback((hotspot: WorldHotspot) => {
    if (interactionPending) return;
    if (hotspot.kind === "article") {
      const article = ARTICLE_BY_ID.get(hotspot.articleId);
      if (article) setSelectedArticle(article);
      return;
    }
    void onInvestigate?.(hotspot.sceneId, hotspot.id);
  }, [interactionPending, onInvestigate]);

  const engine = useMansionEngine({
    initialPosition,
    initialFacing: playerCharacter.initialFacing,
    blocked: interactionBlocked || selectedArticle !== null || showJournal || showMap,
    worldHotspots,
    onInteractHotspot: interactWithHotspot,
    onMoveInput: () => setShowHelp(false),
    onPlayerPose,
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Escape") return;
      setSelectedArticle(null);
      setShowJournal(false);
      setShowMap(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const nearestHotspot = engine.activeHotspotId
    ? worldHotspots.find((hotspot) => hotspot.id === engine.activeHotspotId) ?? null
    : null;
  const nearestSeat = engine.activeSeatId
    ? demoSeats.find((seat) => seat.id === engine.activeSeatId) ?? null
    : null;
  const seatedChair = engine.seatedChairId
    ? demoSeats.find((seat) => seat.id === engine.seatedChairId) ?? null
    : null;
  const activeRoom = demoRooms.find((room) => room.id === engine.activeRoomId)
    ?? demoRooms.find((room) => room.id === "hall")
    ?? demoRooms[0];
  const promptVisible = !selectedArticle && !interactionBlocked && !showJournal && !showMap;

  return (
    <MotionConfig reducedMotion="user">
      <main
        className="mansion-demo"
        ref={engine.viewportRef}
        data-player-x={Math.round(engine.playerSnapshot.x)}
        data-player-y={Math.round(engine.playerSnapshot.y)}
        data-room={engine.activeRoomId}
        data-seated={engine.seatedChairId ? "true" : undefined}
      >
        <div ref={engine.cameraElementRef} className="demo-world-camera">
          <div className="demo-world" style={{ width: DEMO_WORLD_WIDTH, height: DEMO_WORLD_HEIGHT }}>
            <StaticScene
              activeHotspotId={engine.activeHotspotId}
              hotspots={worldHotspots}
              interactionPending={interactionPending}
              onInteract={engine.interactHotspot}
              activeRoomId={engine.activeRoomId}
              characters={sceneCharacters}
            />
            <CharacterSprite
              character={playerCharacter}
              avatarCharacterId={playerCharacterId}
              player
              facing={engine.playerFacing}
              moving={engine.playerMoving}
              elementRef={engine.playerElementRef}
              position={seatedChair?.seat.position ?? engine.playerRef.current}
              seatedFacing={seatedChair?.seat.facing}
            />
          </div>
        </div>

        <div className="demo-vignette" />
        <div className="demo-dust" aria-hidden="true" />

        <SceneMiniMap
          activeRoom={activeRoom}
          companions={sceneCharacters.map(({ character }) => character)}
          player={engine.playerSnapshot}
        />

        <header className="demo-hud-top">
          <div className="demo-location-card">
            <span className="demo-location-index">01</span>
            <div><p>旧剧场 · {activeRoom.name}</p><span>{stageName ?? "前端视觉与操作原型"}</span></div>
          </div>
          <nav className="demo-hud-actions" aria-label="游戏界面操作">
            <button type="button" onClick={() => setShowMap(true)}><MapIcon /><span>地图</span></button>
            <button
              type="button"
              aria-label={journalLabel}
              onClick={() => onOpenJournal ? onOpenJournal() : setShowJournal(true)}
            ><BookOpen /><span>{journalLabel}</span></button>
            <button type="button" onClick={() => setMuted((value) => !value)}>{muted ? <X /> : <Volume2 />}<span>{muted ? "静音" : "环境音"}</span></button>
            <button type="button" onClick={() => setShowHelp((value) => !value)}><Menu /><span>操作</span></button>
          </nav>
        </header>

        <aside className="demo-objective-card">
          <span>{stageName ? `当前阶段 · ${stageName}` : `探索模式 · ${activeRoom.name}`}</span>
          <p>{objectiveText ?? (stageName ? "在精致地图中靠近发光热点，调查 YAML 剧本当前允许的内容。" : "在旧剧场中自由行走，靠近发光标记阅读静态剧情组件。")}</p>
          <div><Footprints /> WASD / 方向键移动</div>
        </aside>

        <AnimatePresence>
          {seatedChair && promptVisible && (
            <motion.button
              type="button"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="demo-interact-prompt is-seat-action"
              onClick={engine.standUp}
            >
              <kbd>E</kbd><Armchair aria-hidden="true" /><span>起身</span><strong>圆桌座位</strong>
            </motion.button>
          )}
          {!seatedChair && nearestSeat && promptVisible && (
            <motion.button
              type="button"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="demo-interact-prompt is-seat-action"
              onClick={() => engine.sitDown(nearestSeat.id)}
            >
              <kbd>E</kbd><Armchair aria-hidden="true" /><span>坐下</span><strong>圆桌座位</strong>
            </motion.button>
          )}
          {!seatedChair && !nearestSeat && nearestHotspot && promptVisible && (
            <motion.button
              type="button"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="demo-interact-prompt"
              onClick={engine.interact}
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
          <span className="demo-status-coordinate">X {Math.round(engine.playerSnapshot.x)} · Y {Math.round(engine.playerSnapshot.y)}</span>
        </div>

        {overlay}

        <AnimatePresence>
          {showHelp && (
            <motion.div className="demo-help-card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 14 }}>
              <CircleHelp />
              <div><strong>移动与场景交互</strong><span>使用 WASD / 方向键行走，靠近光点或圆桌座位按 E 交互。</span></div>
              <button type="button" onClick={() => setShowHelp(false)}>知道了</button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="demo-touch-pad" aria-label="触控方向键">
          {TOUCH_DIRECTIONS.map((direction) => (
            <button
              key={direction.label}
              type="button"
              aria-label={direction.label}
              onPointerDown={(event) => engine.setTouchDirection(event, direction.x, direction.y)}
              onPointerUp={engine.clearTouchDirection}
              onPointerCancel={engine.clearTouchDirection}
              onLostPointerCapture={engine.resetTouchDirection}
            >
              {direction.symbol}
            </button>
          ))}
        </div>

        <AnimatePresence>
          {selectedArticle && <StoryArticlePanel article={selectedArticle} onClose={() => setSelectedArticle(null)} />}
        </AnimatePresence>

        {includeDemoContent && (
          <JournalOverlay
            open={showJournal}
            onClose={() => setShowJournal(false)}
            onSelectArticle={(article) => {
              setShowJournal(false);
              setSelectedArticle(article);
            }}
          />
        )}

        <MapOverlay open={showMap} onClose={() => setShowMap(false)} player={engine.playerSnapshot} />
      </main>
    </MotionConfig>
  );
}
