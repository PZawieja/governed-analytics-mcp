import threading

import psycopg
from psycopg import errors, sql

from governed_analytics_mcp.backends import (
    AccessDenied,
    QueryResult,
    json_safe,
    safe_params,
)
from governed_analytics_mcp.compiler import (
    CompiledQuery,
    MetricRequest,
    compile_request,
)
from governed_analytics_mcp.identity import Asker
from governed_analytics_mcp.metrics import Catalog


class PostgresBackend:
    """Runs every query as the asker's role, so RLS and grants decide the rows.

    With set_role=False it runs as whoever the URL logs in as: the shared-account
    setup the post warns about, kept only so the evals can show it leaking.
    """

    def __init__(self, url: str, catalog: Catalog, set_role: bool = True):
        self.catalog = catalog
        self.set_role = set_role
        self.name = "postgres" if set_role else "postgres-shared-account"
        self.enforcement = (
            "warehouse RLS as the asker" if set_role else "none (shared account)"
        )
        self._url = url
        self._lock = threading.Lock()
        self._conn: psycopg.Connection | None = None

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._url)
        return self._conn

    def compile(self, asker: Asker, request: MetricRequest) -> CompiledQuery:
        return compile_request(self.catalog, request, placeholder="%s")

    def execute(self, asker: Asker, compiled: CompiledQuery) -> QueryResult:
        with self._lock:
            conn = self._connection()
            try:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("SET LOCAL statement_timeout = '5s'")
                    if self.set_role:
                        cur.execute(
                            sql.SQL("SET LOCAL ROLE {}").format(
                                sql.Identifier(asker.role)
                            )
                        )
                    cur.execute("SELECT current_user")
                    ran_as = cur.fetchone()[0]
                    cur.execute(compiled.sql, compiled.params)
                    rows = [[json_safe(v) for v in r] for r in cur.fetchall()]
            except errors.InsufficientPrivilege as exc:
                raise AccessDenied(
                    f"{compiled.metric.name} is not available for your access "
                    f"(warehouse said: {exc.diag.message_primary})"
                ) from None
        return QueryResult(
            columns=compiled.columns,
            rows=rows,
            sql=compiled.sql,
            params=safe_params(compiled.params),
            ran_as=ran_as,
            enforcement=self.enforcement,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
