SELECT
    store_id
    , store_name
    , city
    , region
    , opened_on
FROM {{ ref('raw_stores') }}
