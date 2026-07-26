import { Map as MapIcon } from "lucide-react";
import { memo } from "react";

import {
  DEMO_WORLD_HEIGHT,
  DEMO_WORLD_WIDTH,
  demoDoorFrames,
  demoRooms,
  type DemoPoint,
  type DemoRoom,
  type SceneCharacter,
} from "@/lib/demo-data";

import { pointToMapStyle, rectToMapStyle } from "./mapProjection";

/** 右上角常驻方位图：世界坐标线性映射到百分比布局 */
export const SceneMiniMap = memo(function SceneMiniMap({
  activeRoom,
  companions,
  player,
}: {
  activeRoom: DemoRoom;
  companions: Pick<SceneCharacter, "id" | "x" | "y">[];
  player: DemoPoint;
}) {
  return (
    <aside className="demo-corner-map" aria-label="场景小地图">
      <header><MapIcon /><strong>方位图</strong><span>{activeRoom.name}</span></header>
      <div className="demo-corner-map-canvas">
        {demoRooms.map((room) => (
          <div
            key={room.id}
            className={`demo-corner-room ${room.id === activeRoom.id ? "is-current" : ""}`}
            style={rectToMapStyle(room.bounds)}
          >
            <span>{room.name}</span>
          </div>
        ))}
        {demoDoorFrames.map((door) => (
          <i
            key={door.id}
            className="demo-corner-door"
            style={{
              left: `${(door.x / DEMO_WORLD_WIDTH) * 100}%`,
              top: `${(door.y / DEMO_WORLD_HEIGHT) * 100}%`,
              width: `${Math.max(1.5, (door.width / DEMO_WORLD_WIDTH) * 100)}%`,
              height: `${Math.max(4, (door.height / DEMO_WORLD_HEIGHT) * 100)}%`,
            }}
          />
        ))}
        {companions.map((companion) => (
          <i
            key={companion.id}
            className="demo-corner-person"
            style={pointToMapStyle(companion)}
          />
        ))}
        <i className="demo-corner-person is-player" style={pointToMapStyle(player)} />
      </div>
    </aside>
  );
});
