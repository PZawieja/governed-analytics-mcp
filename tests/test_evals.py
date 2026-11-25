import pytest

from governed_analytics_mcp.app import make_service
from governed_analytics_mcp.evals import gate, load_cases, run_tool_evals


def run(backend, keyed_by="asker"):
    service = make_service(backend, cache_keyed_by=keyed_by, audit_path=None)
    return gate(run_tool_evals(service, load_cases()))


def test_duckdb_passes_with_zero_leaks(catalog):
    assert run("duckdb") == {"passed": True, "reasons": []}


@pytest.mark.postgres
def test_postgres_passes_with_zero_leaks(pg):
    assert run("postgres") == {"passed": True, "reasons": []}


@pytest.mark.postgres
def test_gate_catches_the_shared_account(pg):
    verdict = run("postgres-shared-account")
    assert not verdict["passed"]
    assert "leak" in verdict["reasons"][0]


@pytest.mark.postgres
def test_gate_catches_a_question_keyed_cache(pg):
    # With RLS every asker sends identical SQL, so a key without the asker collides.
    verdict = run("postgres", keyed_by="sql_only")
    assert not verdict["passed"]
    assert "post-emma-by-region" in verdict["reasons"][0]
