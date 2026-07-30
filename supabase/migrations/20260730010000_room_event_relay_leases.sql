-- T11 durable relay leases, retry fencing, and poison quarantine.

ALTER TABLE public.room_outbox
    ADD COLUMN lease_token UUID,
    ADD COLUMN lease_owner TEXT,
    ADD COLUMN lease_expires_at TIMESTAMPTZ,
    ADD COLUMN poisoned_at TIMESTAMPTZ,
    ADD COLUMN poison_reason TEXT;

ALTER TABLE public.room_outbox
    ADD CONSTRAINT room_outbox_lease_check CHECK (
        (lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)
        OR (
            lease_token IS NOT NULL
            AND lease_owner IS NOT NULL
            AND length(btrim(lease_owner)) > 0
            AND lease_expires_at IS NOT NULL
        )
    ),
    ADD CONSTRAINT room_outbox_poison_check CHECK (
        (poisoned_at IS NULL AND poison_reason IS NULL)
        OR (
            poisoned_at IS NOT NULL
            AND poison_reason IS NOT NULL
            AND length(btrim(poison_reason)) > 0
        )
    ),
    ADD CONSTRAINT room_outbox_terminal_state_check CHECK (
        NOT (published_at IS NOT NULL AND poisoned_at IS NOT NULL)
        AND (
            published_at IS NULL
            OR (lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)
        )
        AND (
            poisoned_at IS NULL
            OR (lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)
        )
    );

DROP INDEX public.idx_room_outbox_pending;

CREATE INDEX idx_room_outbox_pending
    ON public.room_outbox(available_at, id)
    WHERE published_at IS NULL AND poisoned_at IS NULL;

CREATE INDEX idx_room_outbox_lease_expiry
    ON public.room_outbox(lease_expires_at, id)
    WHERE published_at IS NULL
      AND poisoned_at IS NULL
      AND lease_token IS NOT NULL;

CREATE INDEX idx_room_outbox_poisoned
    ON public.room_outbox(poisoned_at, id)
    WHERE poisoned_at IS NOT NULL;

REVOKE ALL PRIVILEGES ON TABLE public.room_outbox FROM anon, authenticated;
GRANT ALL PRIVILEGES ON TABLE public.room_outbox TO service_role;

COMMENT ON COLUMN public.room_outbox.lease_token IS
    'Fences relay acknowledgement to the exact committed delivery claim.';
COMMENT ON COLUMN public.room_outbox.lease_owner IS
    'Opaque worker identifier for operational diagnostics; never a room or participant id.';
COMMENT ON COLUMN public.room_outbox.lease_expires_at IS
    'Expired claims may be reclaimed and can cause duplicate delivery with the same event identity.';
COMMENT ON COLUMN public.room_outbox.poisoned_at IS
    'Set after the configured failure threshold so later healthy events remain claimable.';
COMMENT ON COLUMN public.room_outbox.poison_reason IS
    'Bounded exception class only; payloads and participant identifiers must not be stored here.';
