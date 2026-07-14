ALTER TABLE public.chat_messages
    ADD COLUMN IF NOT EXISTS engine_message_id text;

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_messages_session_engine_message
    ON public.chat_messages (session_id, engine_message_id);

COMMENT ON COLUMN public.chat_messages.engine_message_id IS
    'Stable GameState message ID used to make graph projection idempotent.';
