-- Run once as a superuser. Idempotent.
DO $$
DECLARE
    persona TEXT;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'transformer') THEN
        CREATE ROLE transformer LOGIN PASSWORD 'transformer';
    END IF;
    -- The agent's login. It owns nothing and, with NOINHERIT, can read nothing
    -- until it switches to the asker's role.
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'agent_gateway') THEN
        CREATE ROLE agent_gateway LOGIN NOINHERIT PASSWORD 'agent_gateway';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'all_regions_reader') THEN
        CREATE ROLE all_regions_reader NOLOGIN;
    END IF;
    FOREACH persona IN ARRAY ARRAY['emma', 'jake', 'dana', 'sam'] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = persona) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', persona);
        END IF;
    END LOOP;
END
$$;

GRANT CREATE ON DATABASE copper_kettle TO transformer;
GRANT analyst TO emma, jake, dana, sam;
GRANT all_regions_reader TO jake;
GRANT emma, jake, dana, sam TO agent_gateway WITH INHERIT FALSE, SET TRUE;  -- noqa: PRS
