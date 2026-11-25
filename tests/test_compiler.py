from datetime import date

import pytest

from governed_analytics_mcp.compiler import (
    MetricRequest,
    Predicate,
    QueryError,
    compile_request,
)


def test_compiles_to_parameterized_sql(catalog):
    req = MetricRequest.build(
        "revenue", ["region"], {"region": "Oregon"}, "2026-10-01", "2026-10-31"
    )
    q = compile_request(catalog, req, "%s")
    assert q.sql.startswith('SELECT "region" AS "region", SUM(revenue_usd)')
    assert 'FROM "marts"."fct_store_sales"' in q.sql
    assert q.params == ["Oregon", date(2026, 10, 1), date(2026, 10, 31)]
    assert q.columns == ["region", "revenue"]


def test_filter_values_never_reach_the_sql_text(catalog):
    evil = "Oregon') OR 1=1 --"
    q = compile_request(
        catalog, MetricRequest.build("revenue", filters={"region": evil}), "?"
    )
    assert evil not in q.sql
    assert q.params == [evil]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"metric": "profit"}, "unknown metric"),
        ({"metric": "revenue", "group_by": ["customer_email"]}, "can't be grouped"),
        ({"metric": "revenue", "filters": {"1=1; DROP": "x"}}, "can't be grouped"),
        ({"metric": "company_revenue", "group_by": ["region"]}, "can't be grouped"),
        ({"metric": "revenue", "start": "last october"}, "ISO date"),
    ],
)
def test_rejects_anything_outside_the_catalog(catalog, kwargs, message):
    with pytest.raises(QueryError, match=message):
        compile_request(catalog, MetricRequest.build(**kwargs), "?")


def test_rejects_non_string_filter_values():
    with pytest.raises(QueryError):
        MetricRequest.build("revenue", filters={"region": [1, 2]})


def test_request_normalization_makes_equal_requests_equal():
    a = MetricRequest.build("revenue", ["region", "region"], {"region": ["WA", "OR"]})
    b = MetricRequest.build("revenue", ["region"], {"region": ["OR", "WA", "OR"]})
    assert a == b


def test_extra_predicates_use_the_backend_placeholder(catalog):
    pred = Predicate('"region" IN (SELECT region FROM t WHERE u = {p})', ("emma",))
    q = compile_request(catalog, MetricRequest.build("revenue"), "?", [pred])
    assert "WHERE u = ?" in q.sql
    assert q.params == ["emma"]
