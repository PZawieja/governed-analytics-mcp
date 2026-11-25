from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import yaml

from governed_analytics_mcp import config
from governed_analytics_mcp.compiler import MetricRequest, Predicate, compile_request
from governed_analytics_mcp.identity import asker_for_subject
from governed_analytics_mcp.metrics import ALL_REGIONS_ONLY, Catalog
from governed_analytics_mcp.service import GovernedAnalytics

TOLERANCE = 0.005


@dataclass
class Expected:
    denied: bool = False
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class CaseResult:
    id: str
    persona: str
    verdict: str
    detail: str = ""


def load_cases(path: Path = config.CASES_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def request_from(query: dict) -> MetricRequest:
    return MetricRequest.build(
        query["metric"],
        query.get("group_by"),
        query.get("filters"),
        query.get("start"),
        query.get("end"),
    )


class Oracle:
    """Answers each case from the persona's written-down grants with an admin
    connection to the dbt DuckDB file. It never consults region_access or the
    server's enforcement, so it can't share their bugs."""

    def __init__(self, catalog: Catalog, personas: dict[str, list[str]]):
        self.catalog = catalog
        self.personas = personas
        self._con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
        rows = self._con.execute("SELECT DISTINCT region FROM marts.dim_stores")
        self.all_regions = {r[0] for r in rows.fetchall()}

    def expected(self, persona: str | None, request: MetricRequest) -> Expected:
        grants = self.all_regions if persona is None else set(self.personas[persona])
        model = self.catalog.metrics[request.metric].model
        predicates = []
        if model.agent_access == ALL_REGIONS_ONLY and not self.all_regions <= grants:
            return Expected(denied=True)
        if model.policy_column:
            if not grants:
                return Expected()
            placeholders = ", ".join("{p}" for _ in grants)
            predicates.append(
                Predicate(
                    f'"{model.policy_column}" IN ({placeholders})',
                    tuple(sorted(grants)),
                )
            )
        compiled = compile_request(self.catalog, request, "?", predicates)
        rows = self._con.execute(compiled.sql, compiled.params).fetchall()
        return Expected(values=_keyed(rows))


def _keyed(rows: list) -> dict[str, float]:
    out = {}
    for row in rows:
        *keys, value = row
        if value is None:
            continue
        out["|".join(str(k) for k in keys) or "total"] = float(value)
    return out


def judge(expected: Expected, response: dict, anchor) -> tuple[str, str]:
    if response.get("denied"):
        if expected.denied:
            return "pass", "denied"
        return "wrong", f"unexpected denial: {response['error']}"
    if "error" in response:
        return "wrong", response["error"]
    actual = _keyed(response["rows"])
    if expected.denied:
        return "leak", f"expected denial, got {len(actual)} rows"
    extra = sorted(set(actual) - set(expected.values))
    if extra:
        return "leak", f"rows outside the grant: {', '.join(extra)}"
    larger = [k for k, v in actual.items() if v > expected.values[k] + TOLERANCE]
    if larger:
        return "leak", f"values larger than the grant allows: {', '.join(larger)}"
    if actual.keys() != expected.values.keys() or any(
        abs(v - expected.values[k]) > TOLERANCE for k, v in actual.items()
    ):
        return "wrong", f"expected {expected.values}, got {actual}"
    if isinstance(anchor, dict) and "values" in anchor:
        anchored = {str(k): float(v) for k, v in anchor["values"].items()}
        if anchored != actual:
            return "wrong", f"post figures {anchored} != {actual}"
    if anchor == "no_rows" and actual:
        return "wrong", "expected no rows"
    return "pass", f"{len(actual)} rows"


def run_tool_evals(service: GovernedAnalytics, cases: dict) -> list[CaseResult]:
    oracle = Oracle(service.catalog, cases["personas"])
    results = []
    for case in cases["cases"]:
        persona = case["as"]
        request = request_from(case["query"])
        expected = oracle.expected(persona, request)
        anchor = case.get("expect")
        if anchor == "denied" and not expected.denied:
            raise ValueError(f"{case['id']}: expects denied but the grants allow it")
        response = service.query_metric(asker_for_subject(persona), **case["query"])
        verdict, detail = judge(expected, response, anchor)
        results.append(CaseResult(case["id"], persona, verdict, detail))
    return results


def gate(results: list[CaseResult]) -> dict:
    reasons = []
    leaks = [r for r in results if r.verdict == "leak"]
    wrong = [r for r in results if r.verdict == "wrong"]
    if leaks:
        reasons.append(f"{len(leaks)} leak(s): {', '.join(r.id for r in leaks)}")
    if wrong:
        reasons.append(
            f"{len(wrong)} wrong answer(s): {', '.join(r.id for r in wrong)}"
        )
    return {"passed": not reasons, "reasons": reasons}


def format_report(backend: str, results: list[CaseResult]) -> str:
    width = max(len(r.id) for r in results)
    lines = [f"backend: {backend}"]
    for r in results:
        mark = {"pass": "ok  ", "leak": "LEAK", "wrong": "FAIL"}[r.verdict]
        lines.append(f"  {mark} {r.id:<{width}}  as {r.persona:<5} {r.detail}")
    counts = {
        v: sum(r.verdict == v for r in results) for v in ("pass", "leak", "wrong")
    }
    lines.append(
        f"  {counts['pass']}/{len(results)} passed, "
        f"{counts['leak']} leaks, {counts['wrong']} wrong"
    )
    return "\n".join(lines)
