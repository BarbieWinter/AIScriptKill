-- Count confirmed transport failures separately from lease claims and recovery.

ALTER TABLE public.room_outbox
    ADD COLUMN failure_attempts INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT room_outbox_failure_attempts_check CHECK (failure_attempts >= 0);

COMMENT ON COLUMN public.room_outbox.attempts IS
    'Diagnostic claim count, including expired-lease recovery; does not consume poison budget.';
COMMENT ON COLUMN public.room_outbox.failure_attempts IS
    'Confirmed transport failures used for retry backoff and poison quarantine.';
