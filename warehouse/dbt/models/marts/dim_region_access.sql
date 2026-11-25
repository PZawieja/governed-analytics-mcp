{{ config(alias='region_access') }}

SELECT
    user_name || '|' || region AS region_access_id
    , user_name
    , region
FROM {{ ref('stg_region_access') }}
