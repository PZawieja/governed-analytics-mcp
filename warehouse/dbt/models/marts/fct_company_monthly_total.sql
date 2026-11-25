SELECT
    sale_month
    , SUM(revenue_usd) AS revenue_usd
    , SUM(transactions) AS transactions  -- noqa: RF04
FROM {{ ref('fct_store_sales') }}
GROUP BY sale_month
