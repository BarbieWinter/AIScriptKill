# Script And Gameplay Domain

## Product Boundary

The core domain is a fixed-script AI murder mystery. `/doc/剧本系统设计.md` is the best product source: the system should protect the determinism of a high-quality mystery while using AI for immersion, natural interaction, controlled stage progression, and review.

AI may:

- Perform as DM and NPCs.
- Answer naturally within current stage and character knowledge.
- Control flow and trigger clues, evidence, scenes, and media.
- Help with final review and scoring.

AI should not:

- Change the culprit, motive, or key evidence.
- Invent mainline story facts.
- Reveal locked clues, DM-only material, or future-stage information.
- Expose backend/sales/DM materials to players.

This boundary explains why the repo emphasizes script packages, RLS, visibility metadata, package schemas, and Guard/RAG concepts.

## Main Domain Concepts

### Script Package

A script package is the content unit. `/docs/SCRIPT_PACKAGE_SCHEMA.md` describes the intended directory shape with `package.yml`, `stages/`, `characters/`, `clues/`, `evidences/`, `scenes/`, `media/`, `dm_guide/`, `endings.yml`, and `assets/`.

Current backend import is zip-based. `engine/core/package_loader.py` expects exactly one `package.yml` in the uploaded archive, validates it through `engine/core/package_schema.py`, and loads structure rows into database tables.

Required by current loader:

- `package.yml` with `metadata.id`, `metadata.title`, `metadata.version`, and `engine.entry_stage`.
- At least one stage YAML under `stages/`.
- At least one character YAML under `characters/`.

Optional but supported by current loader:

- `characters/_index.yml` for playable/order metadata.
- `clues/rounds/*.yml` for clue rounds.
- `evidences/*.yml`.
- `scenes/*.yml`.
- `media/*.yml` with audio/image asset lists.

### Stage

A stage is the unit of game progression. Design docs describe stages as controlled rounds/acts with entry and exit conditions. Current backend stores full stage definitions in `script_stages.definition` and uses a small subset when creating sessions: `available_actions`, `available_characters`, and `available_scenes` from `engine/repositories/session_seed.py`.

If a stage omits available actions, current backend defaults to `talk_to_npc`, `examine_scene`, and `open_clue_board`. If it omits scenes, the current scene defaults to `start`.

### Character

Characters may be playable, NPCs, or a DM alter ego. Current package loading reads character files and optional `_index.yml` metadata into `script_characters`, with `is_playable`, `is_dm_alter_ego`, and `sort_order`.

The product design requires character knowledge boundaries: NPCs should only know what their role and current stage allow. That is not fully implemented yet; current action replies are canned placeholders.

### Clues And Evidences

Clues and evidences are separate concepts in source and schema:

- Clues are investigation facts, stored in `script_clues`, unlockable through `session_discoveries` with `entity_type='clue'`.
- Evidences are props, key evidence, skill cards, or ordinary evidence, stored in `script_evidences`, also tracked in discoveries when found.

RLS and query code use metadata such as stage visibility and character visibility to prevent spoilers. Current backend action logic only unlocks a fixed `broken_glass` clue for `examine_scene`.

### Scenes And Media

Scenes are interactive locations with backgrounds/hotspots in the intended design. Current backend stores scene definitions and background URLs, but the live backend does not yet evaluate hotspots from package content. Frontend mock gameplay has the richest scene/hotspot implementation in `apps/web/lib/mock-data.ts` and `components/game/SceneHotspots.tsx`.

Media assets are stored in `script_media`, with types such as `bgm`, `story`, `sfx`, `voice`, `image`, and `video`. `engine/media/orchestrator.py` is still a placeholder.

### DM Guide, Truth, And Review

The design docs treat DM materials and truth data as privileged content. Current backend package loader does not yet ingest `dm_guide/` or `endings.yml`, and scoring/review logic is placeholder-level in `engine/services/action_mappers.py` and `engine/repositories/session_mutations.py`.

## Snow Village Status

The repository includes Snow Village assets and design references:

- `/doc/剧本系统设计.md` describes `Organizing/` as containing script PDFs, clues, audio, posters, props, DM materials, and operating assets.
- `apps/web/lib/mock-data.ts` contains executable mock Snow Village gameplay data.
- `/script-packages/snow-village` contains the expected package directories but no package YAML files in the inspected tree.

Do not assume Snow Village has been converted into an importable backend package yet. If converting it, use `/docs/SCRIPT_PACKAGE_SCHEMA.md` and `engine/core/package_loader.py` as the binding contract, and reconcile mock-data inconsistencies before treating it as canonical.

## Condition DSL

`/docs/CONDITION_DSL_REFERENCE.md` defines an intended YAML DSL for stage progression, clue/evidence checks, dialogue checks, player actions, and boolean composition. Current `engine/core/condition_evaluator.py` is a placeholder, so this DSL is not active runtime behavior yet.

## Change Guidance

When changing domain behavior, decide whether you are changing:

- The product/design specification in `docs/` or `doc/`.
- The importable package contract in `engine/core/package_schema.py` and `package_loader.py`.
- The database representation in `supabase/migrations/` and `engine/db/tables.py`.
- The runtime behavior in services/repositories.
- The frontend mock experience in `apps/web/lib/mock-data.ts`.

Keep these layers aligned. Mismatches already exist between target docs, mock gameplay, empty package directories, and backend placeholder behavior.
