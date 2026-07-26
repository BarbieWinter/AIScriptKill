-- Bind each outbox routing session to the referenced immutable event session.

ALTER TABLE public.session_events
    ADD CONSTRAINT uq_session_events_session_id UNIQUE (session_id, id);

ALTER TABLE public.room_outbox
    DROP CONSTRAINT room_outbox_room_event_id_fkey,
    ADD CONSTRAINT fk_room_outbox_session_event
        FOREIGN KEY (session_id, room_event_id)
        REFERENCES public.session_events(session_id, id)
        ON DELETE CASCADE;
