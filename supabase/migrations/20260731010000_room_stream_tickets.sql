-- One-time credentials for authenticated multiplayer room WebSocket handshakes.

CREATE TABLE public.room_stream_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.game_sessions(id) ON DELETE CASCADE,
    member_id UUID NOT NULL,
    principal_id UUID NOT NULL,
    ticket_hash BYTEA NOT NULL,
    protocol_version SMALLINT NOT NULL DEFAULT 1,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_room_stream_tickets_hash UNIQUE (ticket_hash),
    CONSTRAINT fk_room_stream_tickets_member FOREIGN KEY (
        member_id,
        session_id,
        principal_id
    ) REFERENCES public.room_members(id, session_id, principal_id) ON DELETE CASCADE,
    CONSTRAINT room_stream_tickets_hash_check CHECK (octet_length(ticket_hash) = 32),
    CONSTRAINT room_stream_tickets_protocol_check CHECK (protocol_version = 1),
    CONSTRAINT room_stream_tickets_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT room_stream_tickets_consumed_check CHECK (
        consumed_at IS NULL OR consumed_at >= created_at
    ),
    CONSTRAINT room_stream_tickets_revoked_check CHECK (
        revoked_at IS NULL OR revoked_at >= created_at
    )
);

CREATE INDEX idx_room_stream_tickets_member_active
    ON public.room_stream_tickets(session_id, member_id, expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;

ALTER TABLE public.room_stream_tickets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.room_stream_tickets
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE public.room_stream_tickets FROM anon, authenticated;
GRANT ALL PRIVILEGES ON TABLE public.room_stream_tickets TO service_role;

COMMENT ON TABLE public.room_stream_tickets IS
    'Short-lived one-time bearer credentials for authenticated room stream handshakes.';
COMMENT ON COLUMN public.room_stream_tickets.ticket_hash IS
    'SHA-256 digest only; plaintext is returned once by the authenticated HTTP endpoint.';
COMMENT ON COLUMN public.room_stream_tickets.consumed_at IS
    'Set atomically only when the bound member is still joined to the requested room.';
