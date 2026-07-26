-- Store only each joined member's latest non-authoritative scene pose.
-- Gameplay state, revision, events, and frozen packages remain untouched.

ALTER TABLE public.room_members
    ADD COLUMN scene_x double precision,
    ADD COLUMN scene_y double precision,
    ADD COLUMN scene_facing text,
    ADD COLUMN scene_moving boolean,
    ADD COLUMN scene_updated_at timestamptz,
    ADD CONSTRAINT room_members_scene_presence_check CHECK (
        (
            scene_x IS NULL
            AND scene_y IS NULL
            AND scene_facing IS NULL
            AND scene_moving IS NULL
            AND scene_updated_at IS NULL
        )
        OR
        (
            scene_x BETWEEN 17 AND 2383
            AND scene_y BETWEEN 17 AND 1583
            AND scene_facing IN ('left', 'right')
            AND scene_moving IS NOT NULL
            AND scene_updated_at IS NOT NULL
        )
    );

COMMENT ON COLUMN public.room_members.scene_x IS
    'Latest client-reported presentation-only X coordinate; never gameplay authority.';
COMMENT ON COLUMN public.room_members.scene_y IS
    'Latest client-reported presentation-only Y coordinate; never gameplay authority.';
COMMENT ON COLUMN public.room_members.scene_facing IS
    'Latest client-reported presentation-only left/right facing.';
COMMENT ON COLUMN public.room_members.scene_moving IS
    'Latest client-reported presentation-only movement flag.';
COMMENT ON COLUMN public.room_members.scene_updated_at IS
    'Database-observed time for deriving short-lived scene presence freshness.';
