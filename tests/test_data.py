import duckdb

from governed_analytics_mcp import config


def test_october_matches_the_post(catalog):
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    rows = dict(
        con.execute(
            "SELECT region, SUM(revenue_usd) FROM marts.fct_store_sales "
            "WHERE sale_month = DATE '2026-10-01' GROUP BY 1"
        ).fetchall()
    )
    assert float(rows["Oregon"]) == 680_000
    assert float(sum(rows.values())) == 2_700_000
    total = con.execute(
        "SELECT revenue_usd FROM marts.fct_company_monthly_total "
        "WHERE sale_month = DATE '2026-10-01'"
    ).fetchone()[0]
    assert float(total) == 2_700_000
