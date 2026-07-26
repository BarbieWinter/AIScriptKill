import { memo, type CSSProperties } from "react";

import {
  demoCharacters,
  type DemoCharacter,
  type DemoFurniture,
  type DemoPoint,
  type SceneCharacter,
} from "@/lib/demo-data";

import { sceneZ } from "./geometry";
import type { SceneAvatar } from "./types";

/** 人物外观全部走 CSS 变量：换装、调色、动画节奏都由数据驱动，不改样式表 */
function characterStyle(character: SceneCharacter, position: DemoPoint = character): CSSProperties {
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

/** 多人角色 ID 映射到本地形象模板；未知角色回落到默认形象 */
export function multiplayerAvatarTemplate(characterId: string): DemoCharacter {
  if (characterId === "investigator") return demoCharacters[1];
  if (characterId === "insider") return demoCharacters[2];
  return demoCharacters[0];
}

export function sceneCharacterForAvatar(avatar: SceneAvatar): SceneCharacter {
  const template = multiplayerAvatarTemplate(avatar.characterId);
  return {
    ...template,
    id: avatar.id,
    name: avatar.name,
    x: avatar.x,
    y: avatar.y,
    initialFacing: avatar.facing,
  };
}

export interface CharacterSpriteProps {
  character: SceneCharacter;
  avatarCharacterId?: string;
  player?: boolean;
  facing?: SceneCharacter["initialFacing"];
  online?: boolean;
  moving?: boolean;
  elementRef?: React.RefObject<HTMLDivElement | null>;
  position?: DemoPoint;
  seatedFacing?: NonNullable<DemoFurniture["seat"]>["facing"];
}

export const CharacterSprite = memo(function CharacterSprite({
  character,
  avatarCharacterId,
  player = false,
  facing,
  online = true,
  moving = false,
  elementRef,
  position,
  seatedFacing,
}: CharacterSpriteProps) {
  return (
    <div
      ref={elementRef}
      className={`demo-character ${player ? "demo-character-player" : "demo-character-companion"} ${online ? "is-online" : "is-offline"} ${moving ? "is-moving" : ""} is-facing-${facing ?? character.initialFacing} ${seatedFacing ? "is-seated" : ""}`}
      data-character-id={character.id}
      data-avatar-character-id={avatarCharacterId}
      data-scene-x={position?.x ?? character.x}
      data-scene-y={position?.y ?? character.y}
      data-outfit={character.outfit}
      data-accessory={character.accessory}
      data-seat-facing={seatedFacing}
      data-online={online ? "true" : "false"}
      style={characterStyle(character, position)}
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
