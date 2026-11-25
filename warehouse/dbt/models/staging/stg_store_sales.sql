SELECT
    sale_date
    , store_id
    , revenue_usd
    , transactions
FROM {{ ref('raw_store_sales') }}
