SELECT
    sales.store_id || '|' || STRFTIME(sales.sale_date, '%Y-%m-%d') AS store_sale_id
    , sales.sale_date
    , DATE_TRUNC('month', sales.sale_date)::DATE AS sale_month
    , sales.store_id
    , stores.region
    , sales.revenue_usd
    , sales.transactions
FROM {{ ref('stg_store_sales') }} AS sales
INNER JOIN {{ ref('stg_stores') }} AS stores
    ON sales.store_id = stores.store_id
