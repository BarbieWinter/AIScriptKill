-- mp3_command_receipts_events: durable command identity, results, and HTTP replay cursor.
-- Forward-only migration; legacy single-player rows and checkpoint semantics remain compatible.

CREATE TABLE public.session_command_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    command_id UUID NOT NULL,
    actor_principal_id UUID,
    actor_member_id UUID,
    command_kind TEXT NOT NULL DEFAULT 'player_action',
    command_version INTEGER NOT NULL DEFAULT 1,
    request_payload JSONB NOT NULL,
    request_sha256 TEXT NOT NULL,
    expected_revision BIGINT,
    base_revision BIGINT,
    result_revision BIGINT,
    status TEXT NOT NULL,
    result JSONB,
    error_code TEXT,
    error_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    base_checkpoint_id TEXT,
    checkpoint_id TEXT,
    state_sha256 TEXT,
    event_sequence_from BIGINT,
    event_sequence_to BIGINT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_session_command_receipts_session_command UNIQUE (session_id, command_id),
    CONSTRAINT fk_session_command_receipts_actor_member
        FOREIGN KEY (actor_member_id, session_id, actor_principal_id)
        REFERENCES public.room_members(id, session_id, principal_id)
        ON DELETE RESTRICT,
    CONSTRAINT session_command_receipts_kind_check
        CHECK (length(btrim(command_kind)) > 0),
    CONSTRAINT session_command_receipts_version_check
        CHECK (command_version > 0),
    CONSTRAINT session_command_receipts_request_hash_check
        CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT session_command_receipts_status_check
        CHECK (status IN ('processing', 'succeeded', 'rejected', 'failed')),
    CONSTRAINT session_command_receipts_status_payload_check
        CHECK (
            (status = 'succeeded' AND result IS NOT NULL AND error_code IS NULL)
            OR (status IN ('rejected', 'failed') AND result IS NULL AND error_code IS NOT NULL)
            OR (status = 'processing' AND result IS NULL AND error_code IS NULL)
        ),
    CONSTRAINT session_command_receipts_revision_check
        CHECK (
            (expected_revision IS NULL OR expected_revision >= 0)
            AND (base_revision IS NULL OR base_revision >= 0)
            AND (result_revision IS NULL OR result_revision >= 0)
        ),
    CONSTRAINT session_command_receipts_attempt_check
        CHECK (attempt_count > 0),
    CONSTRAINT session_command_receipts_event_range_check
        CHECK (
            (event_sequence_from IS NULL AND event_sequence_to IS NULL)
            OR (
                event_sequence_from IS NOT NULL
                AND event_sequence_to IS NOT NULL
                AND event_sequence_from > 0
                AND event_sequence_to >= event_sequence_from
            )
        ),
    CONSTRAINT session_command_receipts_state_hash_check
        CHECK (state_sha256 IS NULL OR state_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT session_command_receipts_actor_check
        CHECK (
            (actor_member_id IS NULL AND actor_principal_id IS NULL)
            OR (actor_member_id IS NOT NULL AND actor_principal_id IS NOT NULL)
        ),
    CONSTRAINT session_command_receipts_completed_check
        CHECK (status = 'processing' OR completed_at IS NOT NULL)
);

CREATE INDEX idx_session_command_receipts_processing
    ON public.session_command_receipts(session_id, status, updated_at)
    WHERE status = 'processing';
CREATE INDEX idx_session_command_receipts_session_created
    ON public.session_command_receipts(session_id, created_at DESC);

ALTER TABLE public.session_checkpoints
    ADD COLUMN command_id UUID;
CREATE INDEX idx_session_checkpoints_session_command
    ON public.session_checkpoints(session_id, command_id, created_at DESC)
    WHERE command_id IS NOT NULL;

CREATE TABLE public.session_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    sequence BIGINT NOT NULL,
    revision BIGINT NOT NULL,
    command_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    state_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_session_events_session_sequence UNIQUE (session_id, sequence),
    CONSTRAINT uq_session_events_session_command UNIQUE (session_id, command_id),
    CONSTRAINT fk_session_events_command
        FOREIGN KEY (session_id, command_id)
        REFERENCES public.session_command_receipts(session_id, command_id)
        ON DELETE CASCADE,
    CONSTRAINT session_events_sequence_check CHECK (sequence > 0),
    CONSTRAINT session_events_revision_check CHECK (revision >= 0),
    CONSTRAINT session_events_type_check CHECK (length(btrim(event_type)) > 0),
    CONSTRAINT session_events_version_check CHECK (event_version > 0),
    CONSTRAINT session_events_state_hash_check
        CHECK (state_sha256 IS NULL OR state_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX idx_session_events_session_sequence
    ON public.session_events(session_id, sequence);

ALTER TABLE public.session_command_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.session_command_receipts
    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_full_access" ON public.session_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE
    public.session_command_receipts,
    public.session_events
FROM anon, authenticated;

GRANT ALL PRIVILEGES ON TABLE
    public.session_command_receipts,
    public.session_events
TO service_role;

COMMENT ON TABLE public.session_command_receipts IS
    'MP-3 durable command identity, canonical request hash, processing lease, and replayable result.';
COMMENT ON COLUMN public.session_command_receipts.command_id IS
    'Client-generated idempotency identity; unique only within one session.';
COMMENT ON COLUMN public.session_command_receipts.request_sha256 IS
    'Lowercase SHA-256 of canonical request payload, excluding command_id.';
COMMENT ON COLUMN public.session_command_receipts.status IS
    'processing is recoverable; terminal statuses are replayed without re-execution.';
COMMENT ON TABLE public.session_events IS
    'Ordered public event cursor for HTTP replay; private runtime state never belongs here.';
COMMENT ON COLUMN public.session_events.sequence IS
    'Strictly increasing per-session replay cursor allocated with the session head.';
COMMENT ON COLUMN public.session_events.payload IS
    'Participant-safe public payload; must not contain hidden state, answers, or package definitions.';
COMMENT ON COLUMN public.session_checkpoints.command_id IS
    'Optional MP-3 command marker used to recover a checkpoint before request projection finalization.';
