SELECT
    user_id || '|' || backend || '|' || STRFTIME(called_on, '%Y-%m-%d') AS agent_query_day_id
    , called_on
    , user_id
    , backend
    , COUNT(*) AS metric_queries
    , COUNT(*) FILTER (WHERE outcome = 'denied') AS denied_queries
    , COUNT(*) FILTER (WHERE outcome = 'invalid') AS invalid_queries
    , COUNT(*) FILTER (WHERE outcome = 'ok' AND rows_returned = 0) AS empty_results
    , COUNT(*) FILTER (WHERE cache_hit) AS cache_hits
    , SUM(rows_returned) AS rows_returned
    , COUNT(DISTINCT sql_hash) AS distinct_queries
    , QUANTILE_CONT(duration_ms, 0.5) AS median_ms
FROM {{ ref('stg_agent_audit_log') }}
WHERE tool = 'query_metric'
GROUP BY called_on, user_id, backend
