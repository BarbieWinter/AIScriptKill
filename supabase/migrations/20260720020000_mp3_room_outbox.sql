-- MP-3 transactional outbox for at-least-once room event publication.

CREATE TABLE public.room_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    room_event_id UUID NOT NULL REFERENCES public.session_events(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_room_outbox_event_topic UNIQUE (room_event_id, topic),
    CONSTRAINT room_outbox_topic_check CHECK (length(btrim(topic)) > 0),
    CONSTRAINT room_outbox_attempts_check CHECK (attempts >= 0)
);

CREATE INDEX idx_room_outbox_pending
    ON public.room_outbox(available_at, id)
    WHERE published_at IS NULL;

ALTER TABLE public.room_outbox ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.room_outbox
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE public.room_outbox FROM anon, authenticated;
GRANT ALL PRIVILEGES ON TABLE public.room_outbox TO service_role;

COMMENT ON TABLE public.room_outbox IS
    'At-least-once publication queue written atomically with its immutable room event.';
COMMENT ON COLUMN public.room_outbox.room_event_id IS
    'Stable consumer idempotency key; consumers deduplicate by this event UUID.';
COMMENT ON COLUMN public.room_outbox.published_at IS
    'Null while pending; set after the topic publisher acknowledges delivery.';
