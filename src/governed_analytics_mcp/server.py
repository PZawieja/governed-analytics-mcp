from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import Field

from governed_analytics_mcp import config
from governed_analytics_mcp.identity import Asker, IdentityError, asker_for_subject
from governed_analytics_mcp.identity import public_key as load_public_key
from governed_analytics_mcp.service import GovernedAnalytics

INSTRUCTIONS = """\
Copper Kettle Coffee sales metrics. Every answer is scoped to the person asking:
the warehouse returns only the rows they may see. You cannot run SQL; use
list_metrics, describe_metric and query_metric. If a result is empty or denied,
say so plainly. Never estimate or infer numbers for data that wasn't returned."""


def jwt_verifier() -> JWTVerifier:
    return JWTVerifier(
        public_key=load_public_key(),
        issuer=config.TOKEN_ISSUER,
        audience=config.TOKEN_AUDIENCE,
    )


def build_server(
    service: GovernedAnalytics,
    *,
    bound_asker: Asker | None = None,
    verifier: JWTVerifier | None = None,
) -> FastMCP:
    """bound_asker is for stdio and in-process use, where the process belongs to
    one person whose token was verified at startup. Over HTTP, every request's
    bearer token is verified and mapped to the asker."""
    mcp = FastMCP("governed-analytics-mcp", instructions=INSTRUCTIONS, auth=verifier)

    def asker() -> Asker:
        if bound_asker is not None:
            return bound_asker
        token = get_access_token()
        if token is None:
            raise ToolError("no verified identity on this request")
        try:
            return asker_for_subject(token.subject)
        except IdentityError as exc:
            raise ToolError(str(exc)) from None

    @mcp.tool
    def list_metrics() -> dict:
        """List the metrics you can query and the dimensions each one allows."""
        return service.list_metrics(asker())

    @mcp.tool
    def describe_metric(metric: str) -> dict:
        """Describe one metric: definition, source model, dimensions, access rule."""
        return service.describe_metric(asker(), metric)

    @mcp.tool
    def query_metric(
        metric: Annotated[str, Field(description="Metric name from list_metrics")],
        group_by: Annotated[
            list[str] | None, Field(description="Dimensions, e.g. ['region']")
        ] = None,
        filters: Annotated[
            dict[str, str | list[str]] | None,
            Field(description="Dimension → value or values, e.g. {'region': 'Oregon'}"),
        ] = None,
        start: Annotated[
            str | None, Field(description="Inclusive ISO date, e.g. 2026-10-01")
        ] = None,
        end: Annotated[
            str | None, Field(description="Inclusive ISO date, e.g. 2026-10-31")
        ] = None,
    ) -> dict:
        """Query a metric. Rows are limited to what the person asking may see."""
        return service.query_metric(asker(), metric, group_by, filters, start, end)

    @mcp.tool
    def explain_last_query() -> dict:
        """Show the SQL behind your last query, the role it ran as, whether it came
        from cache and how access was enforced."""
        return service.explain_last_query(asker())

    return mcp
