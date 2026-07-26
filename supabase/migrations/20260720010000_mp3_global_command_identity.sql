-- Bind every client command UUID to one room and actor across the whole deployment.
-- Existing composite uniqueness remains because session_events references it.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.session_command_receipts
        GROUP BY command_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'MP-3 command identity preflight failed: duplicate command_id values require operator reconciliation';
    END IF;
END
$$;

ALTER TABLE public.session_command_receipts
    ADD CONSTRAINT uq_session_command_receipts_command UNIQUE (command_id);

COMMENT ON CONSTRAINT uq_session_command_receipts_command
    ON public.session_command_receipts IS
    'A client-generated command UUID permanently binds one room, actor, request, and terminal result.';
