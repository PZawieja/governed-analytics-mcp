import psycopg
import pytest
from psycopg import errors

from governed_analytics_mcp import config
from governed_analytics_mcp.app import make_service
from governed_analytics_mcp.identity import asker_for_subject

OCT = {"start": "2026-10-01", "end": "2026-10-31"}
EXPECTED = {
    "emma": {"Oregon": 680000.0},
    "jake": {"California": 870000.0, "Oregon": 680000.0, "Washington": 1150000.0},
    "dana": {"California": 870000.0, "Washington": 1150000.0},
    "sam": {},
}


def by_region(service, user):
    out = service.query_metric(asker_for_subject(user), "revenue", ["region"], **OCT)
    return dict(map(tuple, out["rows"]))


def company(service, user):
    return service.query_metric(asker_for_subject(user), "company_revenue", **OCT)


@pytest.fixture(params=["duckdb", pytest.param("postgres", marks=pytest.mark.postgres)])
def service(request, catalog):
    if request.param == "postgres":
        request.getfixturevalue("pg")
    return make_service(request.param, audit_path=None)


@pytest.mark.parametrize("user", list(EXPECTED))
def test_each_persona_sees_their_regions(service, user):
    assert by_region(service, user) == EXPECTED[user]


def test_summary_table_only_for_all_regions(service):
    assert company(service, "jake")["rows"] == [[2700000.0]]
    for user in ("emma", "dana", "sam"):
        assert company(service, user)["denied"] is True


def test_identity_keyed_cache_does_not_leak(service):
    assert len(by_region(service, "jake")) == 3
    assert by_region(service, "emma") == EXPECTED["emma"]
    assert service.explain_last_query(asker_for_subject("emma"))["cache_hit"] is False
    by_region(service, "emma")
    assert service.explain_last_query(asker_for_subject("emma"))["cache_hit"] is True


def test_explain_reports_role(pg, catalog):
    service = make_service("postgres", audit_path=None)
    by_region(service, "emma")
    explained = service.explain_last_query(asker_for_subject("emma"))
    assert explained["ran_as"] == "emma"
    assert explained["enforcement"] == "warehouse RLS as the asker"


def test_shared_owner_account_sees_everything(pg, catalog):
    service = make_service("postgres-shared-account", audit_path=None)
    assert by_region(service, "emma") == EXPECTED["jake"]


def test_gateway_reads_nothing_on_its_own(pg):
    with psycopg.connect(pg) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM marts.fct_store_sales LIMIT 1")


def test_gateway_cannot_become_the_owner(pg):
    with psycopg.connect(pg) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SET ROLE transformer")


def test_owner_bypasses_rls_as_the_post_says(pg):
    with psycopg.connect(config.TRANSFORMER_URL) as conn:
        rows = conn.execute(
            "SELECT COUNT(DISTINCT region) FROM marts.fct_store_sales"
        ).fetchone()
    assert rows[0] == 3


def test_definer_view_leaks_invoker_view_does_not(pg):
    with psycopg.connect(config.TRANSFORMER_URL, autocommit=True) as owner:
        owner.execute(
            "CREATE OR REPLACE VIEW marts.monthly_total_definer AS "
            "SELECT sale_month, SUM(revenue_usd) AS revenue_usd "
            "FROM marts.fct_store_sales GROUP BY sale_month"
        )
        owner.execute("GRANT SELECT ON marts.monthly_total_definer TO analyst")
    try:
        with psycopg.connect(pg) as conn:
            conn.execute("SET ROLE emma")
            q = "SELECT revenue_usd FROM marts.{} WHERE sale_month = DATE '2026-10-01'"
            definer = conn.execute(q.format("monthly_total_definer")).fetchone()[0]
            invoker = conn.execute(q.format("monthly_total")).fetchone()[0]
        assert float(definer) == 2_700_000
        assert float(invoker) == 680_000
    finally:
        with psycopg.connect(config.TRANSFORMER_URL, autocommit=True) as owner:
            owner.execute("DROP VIEW marts.monthly_total_definer")
