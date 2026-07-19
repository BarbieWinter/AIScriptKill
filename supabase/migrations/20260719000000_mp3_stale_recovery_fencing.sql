-- Fence MP-3 checkpoint writes by the receipt's monotonically increasing command attempt.
-- This migration is forward-only and keeps untagged legacy checkpoints valid.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.session_command_receipts
        WHERE status = 'processing'
        GROUP BY session_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'MP-3 recovery preflight failed: duplicate processing receipts require operator reconciliation';
    END IF;
END
$$;

UPDATE public.session_command_receipts
SET lease_expires_at = now(),
    updated_at = now()
WHERE status = 'processing'
  AND lease_expires_at IS NULL;

ALTER TABLE public.session_command_receipts
    ADD CONSTRAINT session_command_receipts_processing_lease_check
    CHECK (
        (status = 'processing' AND lease_expires_at IS NOT NULL)
        OR (status <> 'processing' AND lease_expires_at IS NULL)
    );

DROP INDEX public.idx_session_command_receipts_processing;
CREATE UNIQUE INDEX uq_session_command_receipts_one_processing
    ON public.session_command_receipts(session_id)
    WHERE status = 'processing';
CREATE INDEX idx_session_command_receipts_processing
    ON public.session_command_receipts(session_id, status, lease_expires_at)
    WHERE status = 'processing';

ALTER TABLE public.session_checkpoints
    ADD COLUMN command_attempt INTEGER;

-- The first MP-3 migration could create command_id before writers attached an attempt.
-- Preserve those rows as attempt 1 so the new paired invariant can be applied online.
UPDATE public.session_checkpoints
SET command_attempt = 1
WHERE command_id IS NOT NULL
  AND command_attempt IS NULL;

ALTER TABLE public.session_checkpoints
    ADD CONSTRAINT session_checkpoints_command_attempt_check
    CHECK (
        (command_id IS NULL AND command_attempt IS NULL)
        OR (
            command_id IS NOT NULL
            AND command_attempt IS NOT NULL
            AND command_attempt > 0
        )
    );

CREATE INDEX idx_session_checkpoints_session_command_attempt
    ON public.session_checkpoints(
        session_id,
        command_id,
        command_attempt,
        thread_ts DESC
    )
    WHERE command_id IS NOT NULL;

ALTER TABLE public.session_command_receipts
    ADD COLUMN base_state JSONB,
    ADD COLUMN base_state_sha256 TEXT,
    ADD CONSTRAINT session_command_receipts_base_state_hash_check
        CHECK (base_state_sha256 IS NULL OR base_state_sha256 ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT session_command_receipts_base_state_check
        CHECK (
            (base_state IS NULL AND base_state_sha256 IS NULL)
            OR (
                base_state IS NOT NULL
                AND jsonb_typeof(base_state) = 'object'
                AND base_state_sha256 IS NOT NULL
            )
        );

COMMENT ON COLUMN public.session_checkpoints.command_attempt IS
    'Positive receipt attempt_count paired with command_id; stale attempts are fenced before checkpoint writes.';
COMMENT ON COLUMN public.session_command_receipts.base_state IS
    'Private canonical merged GameState captured at claim for recovery before the first command checkpoint.';
COMMENT ON COLUMN public.session_command_receipts.base_state_sha256 IS
    'Lowercase SHA-256 of canonical base_state JSON; both base fields are absent only on legacy receipts.';
