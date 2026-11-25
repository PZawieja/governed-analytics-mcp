import threading
from pathlib import Path

import duckdb

from governed_analytics_mcp.backends import (
    AccessDenied,
    QueryResult,
    json_safe,
    safe_params,
)
from governed_analytics_mcp.compiler import (
    CompiledQuery,
    MetricRequest,
    Predicate,
    compile_request,
)
from governed_analytics_mcp.identity import Asker
from governed_analytics_mcp.metrics import ALL_REGIONS_ONLY, Catalog

REGION_ACCESS = "marts.region_access"


class DuckDBBackend:
    """Zero-infra fallback. DuckDB has no row-level security, so this server adds
    the filter itself. That's enforcement in app code: weaker than RLS, because a
    bug here is a leak. Use it to explore locally, not as the production pattern.
    """

    name = "duckdb"
    enforcement = "app-code filter (DuckDB has no RLS)"

    def __init__(self, path: Path, catalog: Catalog):
        self.catalog = catalog
        self._lock = threading.Lock()
        self._con = duckdb.connect(str(path), read_only=True)

    def _regions(self, asker: Asker) -> set[str]:
        rows = self._con.execute(
            f"SELECT region FROM {REGION_ACCESS} WHERE user_name = ?", [asker.user_id]
        ).fetchall()
        return {r[0] for r in rows}

    def _all_regions(self) -> set[str]:
        rows = self._con.execute("SELECT DISTINCT region FROM marts.dim_stores")
        return {r[0] for r in rows.fetchall()}

    def compile(self, asker: Asker, request: MetricRequest) -> CompiledQuery:
        metric = self.catalog.metrics.get(request.metric)
        predicates = []
        if metric is not None and metric.model.policy_column:
            predicates.append(
                Predicate(
                    f'"{metric.model.policy_column}" IN '
                    f"(SELECT region FROM {REGION_ACCESS} WHERE user_name = {{p}})",
                    (asker.user_id,),
                )
            )
        return compile_request(self.catalog, request, "?", predicates)

    def execute(self, asker: Asker, compiled: CompiledQuery) -> QueryResult:
        with self._lock:
            needs_all = compiled.metric.model.agent_access == ALL_REGIONS_ONLY
            if needs_all and not self._all_regions() <= self._regions(asker):
                raise AccessDenied(
                    f"{compiled.metric.name} is not available for your access "
                    "(it needs every region)"
                )
            rows = self._con.execute(compiled.sql, compiled.params).fetchall()
        return QueryResult(
            columns=compiled.columns,
            rows=[[json_safe(v) for v in r] for r in rows],
            sql=compiled.sql,
            params=safe_params(compiled.params),
            ran_as=f"{asker.user_id} (filtered by the server)",
            enforcement=self.enforcement,
        )

    def close(self) -> None:
        self._con.close()
