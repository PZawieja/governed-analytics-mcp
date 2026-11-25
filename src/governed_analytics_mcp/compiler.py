from dataclasses import dataclass, field
from datetime import date

from governed_analytics_mcp.metrics import Catalog, Metric

MAX_ROWS = 500


class QueryError(ValueError):
    pass


@dataclass(frozen=True)
class MetricRequest:
    metric: str
    group_by: tuple[str, ...] = ()
    filters: tuple[tuple[str, tuple[str, ...]], ...] = ()
    start: str | None = None
    end: str | None = None

    @classmethod
    def build(
        cls,
        metric: str,
        group_by: list[str] | None = None,
        filters: dict[str, str | list[str]] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> "MetricRequest":
        normalized = []
        for dim, value in sorted((filters or {}).items()):
            values = [value] if isinstance(value, str) else list(value)
            if not values or not all(isinstance(v, str) for v in values):
                raise QueryError(f"filter {dim!r} needs a string or a list of strings")
            normalized.append((dim, tuple(sorted(set(values)))))
        return cls(
            metric=metric,
            group_by=tuple(dict.fromkeys(group_by or [])),
            filters=tuple(normalized),
            start=start,
            end=end,
        )


@dataclass(frozen=True)
class Predicate:
    sql: str
    params: tuple = ()


@dataclass
class CompiledQuery:
    metric: Metric
    sql: str
    params: list = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise QueryError(f"{label} must be an ISO date like 2026-10-01") from None


def compile_request(
    catalog: Catalog,
    request: MetricRequest,
    placeholder: str,
    extra_predicates: list[Predicate] | None = None,
) -> CompiledQuery:
    metric = catalog.metrics.get(request.metric)
    if metric is None:
        raise QueryError(
            f"unknown metric {request.metric!r}; available: "
            + ", ".join(sorted(catalog.metrics))
        )
    model = metric.model

    def column_for(dim: str) -> str:
        if dim not in model.dimensions:
            raise QueryError(
                f"{request.metric} can't be grouped or filtered by {dim!r}; "
                f"allowed: {', '.join(model.dimensions)}"
            )
        return model.dimensions[dim]

    select = [f"{_ident(column_for(d))} AS {_ident(d)}" for d in request.group_by]
    select.append(f"{metric.expr} AS {_ident(metric.name)}")

    where: list[str] = []
    params: list = []
    for dim, values in request.filters:
        col = column_for(dim)
        where.append(f"{_ident(col)} IN ({', '.join([placeholder] * len(values))})")
        params.extend(values)
    if request.start:
        where.append(f"{_ident(model.time_column)} >= {placeholder}")
        params.append(_parse_date(request.start, "start"))
    if request.end:
        where.append(f"{_ident(model.time_column)} <= {placeholder}")
        params.append(_parse_date(request.end, "end"))
    for pred in extra_predicates or []:
        where.append(pred.sql.replace("{p}", placeholder))
        params.extend(pred.params)

    lines = [f"SELECT {', '.join(select)}", f"FROM {model.qualified}"]
    if where:
        lines.append("WHERE " + "\n  AND ".join(where))
    if request.group_by:
        positions = ", ".join(str(i + 1) for i in range(len(request.group_by)))
        lines.append(f"GROUP BY {positions}")
        lines.append(f"ORDER BY {positions}")
    lines.append(f"LIMIT {MAX_ROWS}")
    return CompiledQuery(
        metric=metric,
        sql="\n".join(lines),
        params=params,
        columns=[*request.group_by, metric.name],
    )
