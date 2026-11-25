import hashlib
import time

from governed_analytics_mcp.audit import AuditLog
from governed_analytics_mcp.backends import (
    AccessDenied,
    Backend,
    QueryResult,
    safe_params,
)
from governed_analytics_mcp.cache import AnswerCache
from governed_analytics_mcp.compiler import MetricRequest, QueryError
from governed_analytics_mcp.identity import Asker
from governed_analytics_mcp.metrics import ALL_REGIONS_ONLY


class GovernedAnalytics:
    def __init__(self, backend: Backend, cache: AnswerCache, audit: AuditLog):
        self.backend = backend
        self.cache = cache
        self.audit = audit
        self._last: dict[str, dict] = {}

    @property
    def catalog(self):
        return self.backend.catalog

    def _log(self, asker: Asker, tool: str, **fields) -> None:
        self.audit.write(
            user_id=asker.user_id,
            role=asker.role,
            backend=self.backend.name,
            tool=tool,
            **fields,
        )

    def list_metrics(self, asker: Asker) -> dict:
        self._log(asker, "list_metrics")
        return {
            "metrics": [
                {
                    "name": m.name,
                    "description": m.description,
                    "dimensions": list(m.model.dimensions),
                }
                for m in self.catalog.metrics.values()
            ]
        }

    def describe_metric(self, asker: Asker, metric: str) -> dict:
        self._log(asker, "describe_metric", metric=metric)
        m = self.catalog.metrics.get(metric)
        if m is None:
            return {"error": f"unknown metric {metric!r}"}
        access = (
            f"rows filtered by {m.model.policy_column} for the asker"
            if m.model.policy_column
            else "only people granted every region"
            if m.model.agent_access == ALL_REGIONS_ONLY
            else "unrestricted"
        )
        return {
            "name": m.name,
            "description": m.description,
            "source_model": m.model.name,
            "time_column": m.model.time_column,
            "dimensions": list(m.model.dimensions),
            "access": access,
        }

    def query_metric(
        self,
        asker: Asker,
        metric: str,
        group_by: list[str] | None = None,
        filters: dict[str, str | list[str]] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        started = time.perf_counter()
        base = {"metric": metric, "group_by": group_by or [], "filters": filters or {}}
        try:
            request = MetricRequest.build(metric, group_by, filters, start, end)
            compiled = self.backend.compile(asker, request)
        except QueryError as exc:
            self._log(asker, "query_metric", **base, outcome="invalid", error=str(exc))
            return {"error": str(exc)}

        key = self.cache.key(
            asker.user_id, self.backend.name, compiled.sql, list(compiled.params)
        )
        result: QueryResult | None = self.cache.get(key)
        cache_hit = result is not None
        if result is None:
            try:
                result = self.backend.execute(asker, compiled)
            except AccessDenied as exc:
                self._remember(asker, compiled, None, False, denied=True)
                self._log(
                    asker,
                    "query_metric",
                    **base,
                    outcome="denied",
                    sql_hash=_sql_hash(compiled.sql),
                    rows=0,
                    cache_hit=False,
                    ms=_ms(started),
                )
                return {"error": str(exc), "denied": True}
            self.cache.put(key, result)

        self._remember(asker, compiled, result, cache_hit)
        self._log(
            asker,
            "query_metric",
            **base,
            outcome="ok",
            sql_hash=_sql_hash(result.sql),
            rows=len(result.rows),
            cache_hit=cache_hit,
            ms=_ms(started),
        )
        return {
            "columns": result.columns,
            "rows": result.rows,
            "row_count": len(result.rows),
            "note": None
            if result.rows
            else "No rows you're allowed to see match this question.",
        }

    def _remember(self, asker, compiled, result, cache_hit, denied=False) -> None:
        self._last[asker.user_id] = {
            "sql": compiled.sql,
            "params": safe_params(list(compiled.params)),
            "ran_as": result.ran_as if result else asker.role,
            "enforcement": self.backend.enforcement,
            "backend": self.backend.name,
            "row_count": len(result.rows) if result else 0,
            "cache_hit": cache_hit,
            "denied": denied,
        }

    def explain_last_query(self, asker: Asker) -> dict:
        self._log(asker, "explain_last_query")
        return self._last.get(asker.user_id, {"note": "no query yet in this session"})


def _sql_hash(sql: str) -> str:
    return hashlib.sha256(" ".join(sql.split()).encode()).hexdigest()[:16]


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
