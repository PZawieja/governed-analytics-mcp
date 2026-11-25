SELECT
    user_name
    , region
FROM {{ ref('raw_region_access') }}
