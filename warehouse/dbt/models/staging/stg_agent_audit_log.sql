SELECT
    MD5(
        CAST(ts AS VARCHAR) || user_id || backend || tool || COALESCE(sql_hash, '')
    ) AS audit_event_id
    , CAST(ts AS TIMESTAMPTZ) AS called_at
    , CAST(CAST(ts AS TIMESTAMPTZ) AS DATE) AS called_on
    , CAST(user_id AS VARCHAR) AS user_id
    , CAST(role AS VARCHAR) AS warehouse_role
    , CAST(backend AS VARCHAR) AS backend
    , CAST(tool AS VARCHAR) AS tool
    , CAST(metric AS VARCHAR) AS metric
    , CAST(outcome AS VARCHAR) AS outcome
    , CAST(sql_hash AS VARCHAR) AS sql_hash
    , CAST(rows AS INTEGER) AS rows_returned
    , COALESCE(CAST(cache_hit AS BOOLEAN), FALSE) AS cache_hit
    , CAST(ms AS INTEGER) AS duration_ms
FROM {{ source('agent', 'audit_log') }}
