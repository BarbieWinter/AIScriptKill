import { BookOpen } from "lucide-react";
import { memo, type CSSProperties } from "react";

import {
  demoDoorFrames,
  demoFurniture,
  demoRooms,
  demoWalls,
  type DemoFurniture,
  type DemoRoom,
  type SceneCharacter,
} from "@/lib/demo-data";

import { CharacterSprite } from "./CharacterSprite";
import { contains, intersects, sceneRenderBounds, sceneZ } from "./geometry";
import type { WorldHotspot } from "./types";

export function hotspotActionLabel(hotspot: WorldHotspot) {
  if (hotspot.kind === "article") return "阅读";
  return hotspot.actionLabel ?? "调查";
}

const doorLabels: Record<string, string> = {
  "kitchen-door": "厨房",
  "study-door": "书房",
  "private-door": "双人讨论室",
  "archive-door": "档案室",
};

export interface StaticSceneCharacter {
  character: SceneCharacter;
  avatarCharacterId?: string;
  moving: boolean;
  online: boolean;
}

/** 场景容器：静态几何、热点与角色各自维护 memo 边界 */
export const StaticScene = memo(function StaticScene({
  activeHotspotId,
  hotspots,
  interactionPending,
  onInteract,
  activeRoomId,
  characters,
}: {
  activeHotspotId: string | null;
  hotspots: WorldHotspot[];
  interactionPending: boolean;
  onInteract: (hotspot: WorldHotspot) => void;
  activeRoomId: DemoRoom["id"];
  characters: StaticSceneCharacter[];
}) {
  return (
    <>
      <FloorLayer activeRoomId={activeRoomId} />
      <div className="demo-depth-layer">
        <GeometryLayer activeRoomId={activeRoomId} />
        <HotspotLayer
          activeHotspotId={activeHotspotId}
          activeRoomId={activeRoomId}
          hotspots={hotspots}
          interactionPending={interactionPending}
          onInteract={onInteract}
        />
        <CharacterLayer characters={characters} />
      </div>
    </>
  );
});

const FloorLayer = memo(function FloorLayer({
  activeRoomId,
}: {
  activeRoomId: DemoRoom["id"];
}) {
  const renderBounds = sceneRenderBounds(activeRoomId);
  return (
    <div className="demo-floor-layer">
      <div className="demo-floor" />
      <div className="demo-stage-glow" />
      <div className="demo-window-light demo-window-light-one" />
      <div className="demo-window-light demo-window-light-two" />
      <div className="demo-carpet" />
      {demoRooms.filter((room) => intersects(room.bounds, renderBounds)).map((room) => (
        <span key={room.id} className="demo-room-label" style={{ left: room.label.x, top: room.label.y }}>
          {room.name}
        </span>
      ))}
    </div>
  );
});

const GeometryLayer = memo(function GeometryLayer({
  activeRoomId,
}: {
  activeRoomId: DemoRoom["id"];
}) {
  const renderBounds = sceneRenderBounds(activeRoomId);
  const visibleWalls = demoWalls.filter((wall) => intersects(wall, renderBounds));
  const visibleFurniture = demoFurniture.filter((entity) => intersects(entity, renderBounds));
  const visibleDoors = demoDoorFrames.filter((door) => intersects(door, renderBounds));

  return (
    <>
      <div className="demo-hall-window" aria-label="窗外正在下雪" style={{ zIndex: sceneZ(320) }}>
        <span className="demo-hall-window-snow">
          {Array.from({ length: 7 }, (_, index) => <i key={index} />)}
        </span>
        <b /><b />
      </div>

      {visibleWalls.map((wall) => (
        <div
          key={wall.id}
          className="demo-wall-volume"
          data-wall-axis={wall.axis}
          data-fade-id={wall.fadeDistance ? wall.id : undefined}
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
          </span>
        </div>
      ))}

      {visibleDoors.map((door) => {
        const horizontal = door.orientation === "horizontal";
        return (
          <div
            key={door.id}
            className="demo-door-frame"
            data-orientation={door.orientation}
            data-door-id={door.id}
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
            <span className="demo-door-leaf" />
            <em>{doorLabels[door.id]}</em>
          </div>
        );
      })}

      {visibleFurniture.map((entity) => (
        <Furniture key={entity.id} entity={entity} />
      ))}
    </>
  );
});

const HotspotLayer = memo(function HotspotLayer({
  activeHotspotId,
  activeRoomId,
  hotspots,
  interactionPending,
  onInteract,
}: {
  activeHotspotId: string | null;
  activeRoomId: DemoRoom["id"];
  hotspots: WorldHotspot[];
  interactionPending: boolean;
  onInteract: (hotspot: WorldHotspot) => void;
}) {
  const renderBounds = sceneRenderBounds(activeRoomId);
  return hotspots.filter((hotspot) => contains(renderBounds, hotspot)).map((hotspot) => (
    <button
      type="button"
      key={hotspot.id}
      data-hotspot-id={hotspot.id}
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
  ));
});

const CharacterLayer = memo(function CharacterLayer({
  characters,
}: {
  characters: StaticSceneCharacter[];
}) {
  return characters.map(({ character, avatarCharacterId, moving, online }) => (
    <CharacterSprite
      key={character.id}
      character={character}
      avatarCharacterId={avatarCharacterId}
      moving={moving}
      online={online}
    />
  ));
});

function Furniture({ entity }: { entity: DemoFurniture }) {
  const baseStyle = {
    left: entity.x,
    top: entity.y,
    width: entity.width,
    height: entity.height,
    rotate: entity.rotation ? `${entity.rotation}deg` : undefined,
    "--furniture-elevation": `${entity.elevation}px`,
  } as CSSProperties;

  // 座椅拆成前后两层，人物坐下时 z-index 正好夹在中间
  if (entity.seat) {
    return (
      <>
        <div
          className="demo-chair-layer demo-chair-back"
          data-seat="available"
          style={{ ...baseStyle, zIndex: sceneZ(entity.sortY - 3) }}
        >
          <span className="demo-chair-backrest" />
          <span className="demo-chair-cushion" />
        </div>
        <div
          className="demo-chair-layer demo-chair-front"
          style={{ ...baseStyle, zIndex: sceneZ(entity.sortY + 3) }}
        >
          <span className="demo-chair-front-edge" />
        </div>
      </>
    );
  }

  return (
    <div
      className="demo-furniture"
      data-kind={entity.kind}
      data-variant={entity.variant}
      data-fade-id={entity.fadeDistance ? entity.id : undefined}
      style={{
        ...baseStyle,
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
