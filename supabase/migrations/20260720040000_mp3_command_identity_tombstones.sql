-- Persist deployment-wide command UUID identity independently of live room retention.

CREATE TABLE public.session_command_identities (
    command_id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    actor_principal_id UUID,
    actor_member_id UUID,
    request_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT session_command_identities_request_hash_check
        CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT session_command_identities_actor_check
        CHECK (
            (actor_member_id IS NULL AND actor_principal_id IS NULL)
            OR (actor_member_id IS NOT NULL AND actor_principal_id IS NOT NULL)
        )
);

CREATE FUNCTION public.reject_bound_session_command_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.session_command_identities
        WHERE command_id = NEW.command_id
    ) THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.bind_inserted_session_command_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    INSERT INTO public.session_command_identities (
        command_id,
        session_id,
        actor_principal_id,
        actor_member_id,
        request_sha256,
        created_at
    ) VALUES (
        NEW.command_id,
        NEW.session_id,
        NEW.actor_principal_id,
        NEW.actor_member_id,
        NEW.request_sha256,
        NEW.created_at
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER reject_bound_session_command_identity_before_insert
BEFORE INSERT ON public.session_command_receipts
FOR EACH ROW EXECUTE FUNCTION public.reject_bound_session_command_identity();

CREATE TRIGGER bind_inserted_session_command_identity_after_insert
AFTER INSERT ON public.session_command_receipts
FOR EACH ROW EXECUTE FUNCTION public.bind_inserted_session_command_identity();

INSERT INTO public.session_command_identities (
    command_id,
    session_id,
    actor_principal_id,
    actor_member_id,
    request_sha256,
    created_at
)
SELECT
    command_id,
    session_id,
    actor_principal_id,
    actor_member_id,
    request_sha256,
    created_at
FROM public.session_command_receipts
ON CONFLICT (command_id) DO NOTHING;

ALTER TABLE public.session_command_identities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access" ON public.session_command_identities
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE public.session_command_identities FROM anon, authenticated;
GRANT ALL PRIVILEGES ON TABLE public.session_command_identities TO service_role;

REVOKE ALL ON FUNCTION public.reject_bound_session_command_identity() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.bind_inserted_session_command_identity() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.reject_bound_session_command_identity() TO service_role;
GRANT EXECUTE ON FUNCTION public.bind_inserted_session_command_identity() TO service_role;

COMMENT ON TABLE public.session_command_identities IS
    'Permanent deployment-wide command UUID tombstones retained after live room deletion.';
