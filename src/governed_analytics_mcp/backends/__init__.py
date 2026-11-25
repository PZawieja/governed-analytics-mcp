import datetime
import decimal
from dataclasses import dataclass, field
from typing import Protocol

from governed_analytics_mcp.compiler import CompiledQuery, MetricRequest
from governed_analytics_mcp.identity import Asker
from governed_analytics_mcp.metrics import Catalog


class AccessDenied(PermissionError):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    sql: str
    params: list = field(default_factory=list)
    ran_as: str = ""
    enforcement: str = ""


def json_safe(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    return value


def safe_params(params: list) -> list:
    return [json_safe(p) for p in params]


class Backend(Protocol):
    name: str
    enforcement: str
    catalog: Catalog

    def compile(self, asker: Asker, request: MetricRequest) -> CompiledQuery: ...

    def execute(self, asker: Asker, compiled: CompiledQuery) -> QueryResult: ...
