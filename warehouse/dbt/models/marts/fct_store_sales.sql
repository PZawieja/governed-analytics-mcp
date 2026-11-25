SELECT
    store_sale_id
    , sale_date
    , sale_month
    , store_id
    , region
    , revenue_usd
    , transactions
FROM {{ ref('int_store_daily_sales') }}
