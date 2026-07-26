-- Clarify the effective scope introduced by deployment-wide live-receipt uniqueness.

COMMENT ON COLUMN public.session_command_receipts.command_id IS
    'Client-generated idempotency identity; unique across all live session receipts.';
