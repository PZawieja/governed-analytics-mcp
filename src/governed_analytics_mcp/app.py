from pathlib import Path

from governed_analytics_mcp import config
from governed_analytics_mcp.audit import AuditLog
from governed_analytics_mcp.cache import AnswerCache
from governed_analytics_mcp.metrics import Catalog, load_catalog
from governed_analytics_mcp.service import GovernedAnalytics

BACKENDS = ("postgres", "duckdb", "postgres-shared-account")


def make_backend(name: str, catalog: Catalog):
    if name == "postgres":
        from governed_analytics_mcp.backends.postgres import PostgresBackend

        return PostgresBackend(config.GATEWAY_URL, catalog)
    if name == "postgres-shared-account":
        from governed_analytics_mcp.backends.postgres import PostgresBackend

        return PostgresBackend(config.TRANSFORMER_URL, catalog, set_role=False)
    if name == "duckdb":
        from governed_analytics_mcp.backends.duckdb import DuckDBBackend

        return DuckDBBackend(config.DUCKDB_PATH, catalog)
    raise ValueError(f"unknown backend {name!r}; choose from {', '.join(BACKENDS)}")


def make_service(
    backend: str = "postgres",
    cache_keyed_by: str = "asker",
    audit_path: Path | None = config.AUDIT_PATH,
) -> GovernedAnalytics:
    catalog = load_catalog(config.METRICS_PATH, config.MANIFEST_PATH)
    return GovernedAnalytics(
        make_backend(backend, catalog),
        AnswerCache(keyed_by=cache_keyed_by),
        AuditLog(audit_path),
    )
