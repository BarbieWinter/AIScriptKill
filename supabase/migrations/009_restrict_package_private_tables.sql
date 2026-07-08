REVOKE ALL PRIVILEGES ON TABLE
    public.script_endings,
    public.script_dm_guides
FROM anon, authenticated;

GRANT ALL PRIVILEGES ON TABLE
    public.script_endings,
    public.script_dm_guides
TO service_role;
