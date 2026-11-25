-- Run as transformer, the owner of every table in marts.

-- The post's policy: you see the regions listed for you in region_access.
ALTER TABLE marts.fct_store_sales ENABLE ROW LEVEL SECURITY;
CREATE POLICY region_scope ON marts.fct_store_sales
FOR SELECT
USING (
    region IN (
        SELECT ra.region
        FROM marts.region_access AS ra
        WHERE ra.user_name = CURRENT_USER
    )
)
;

ALTER TABLE marts.dim_stores ENABLE ROW LEVEL SECURITY;
CREATE POLICY region_scope ON marts.dim_stores
FOR SELECT
USING (
    region IN (
        SELECT ra.region
        FROM marts.region_access AS ra
        WHERE ra.user_name = CURRENT_USER
    )
)
;

-- Users may read their own grants, which is all the policies above need.
ALTER TABLE marts.region_access ENABLE ROW LEVEL SECURITY;
CREATE POLICY own_rows ON marts.region_access
FOR SELECT
USING (user_name = CURRENT_USER)
;

-- A view runs with its owner's rights unless told otherwise. security_invoker
-- makes the policy see the asker, not transformer.
CREATE VIEW marts.monthly_total WITH (security_invoker = TRUE) AS
SELECT
    sale_month
    , SUM(revenue_usd) AS revenue_usd
FROM marts.fct_store_sales
GROUP BY sale_month
;

GRANT USAGE ON SCHEMA marts TO analyst, all_regions_reader;
GRANT SELECT ON marts.fct_store_sales, marts.dim_stores, marts.region_access
, marts.monthly_total TO analyst
;

-- No region column left to filter on, so only people who may see every region.
GRANT SELECT ON marts.fct_company_monthly_total TO all_regions_reader;
