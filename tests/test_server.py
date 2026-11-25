import json
import socket
import threading
import time

import pytest
import uvicorn
from fastmcp import Client

from governed_analytics_mcp.app import make_service
from governed_analytics_mcp.identity import asker_for_subject, mint_token
from governed_analytics_mcp.server import build_server, jwt_verifier

OCT = {"start": "2026-10-01", "end": "2026-10-31"}


def rows(result):
    return result.structured_content["rows"]


async def test_bound_server_answers_as_its_asker(catalog):
    service = make_service("duckdb", audit_path=None)
    server = build_server(service, bound_asker=asker_for_subject("emma"))
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
        assert names == {
            "list_metrics",
            "describe_metric",
            "query_metric",
            "explain_last_query",
        }
        result = await client.call_tool(
            "query_metric", {"metric": "revenue", "group_by": ["region"], **OCT}
        )
        assert rows(result) == [["Oregon", 680000.0]]


async def test_audit_log_records_each_call(catalog, tmp_path):
    path = tmp_path / "audit.jsonl"
    service = make_service("duckdb", audit_path=path)
    server = build_server(service, bound_asker=asker_for_subject("emma"))
    async with Client(server) as client:
        await client.call_tool("query_metric", {"metric": "company_revenue", **OCT})
    record = json.loads(path.read_text().splitlines()[-1])
    assert record["user_id"] == "emma"
    assert record["outcome"] == "denied"


@pytest.fixture(scope="module")
def http_url(catalog):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    service = make_service("duckdb", audit_path=None)
    app = build_server(service, verifier=jwt_verifier()).http_app()
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(5)


async def test_http_maps_each_token_to_its_asker(http_url):
    query = {"metric": "revenue", "group_by": ["region"], **OCT}
    async with Client(http_url, auth=mint_token("emma")) as client:
        assert rows(await client.call_tool("query_metric", query)) == [
            ["Oregon", 680000.0]
        ]
    async with Client(http_url, auth=mint_token("dana")) as client:
        assert len(rows(await client.call_tool("query_metric", query))) == 2


async def test_http_rejects_missing_or_foreign_tokens(http_url):
    with pytest.raises(Exception):  # noqa: B017
        async with Client(http_url) as client:
            await client.list_tools()
    with pytest.raises(Exception):  # noqa: B017
        async with Client(http_url, auth=mint_token("emma", audience="other")) as c:
            await c.list_tools()


async def test_http_token_without_a_role_cannot_query(http_url):
    async with Client(http_url, auth=mint_token("transformer")) as client:
        result = await client.call_tool(
            "query_metric", {"metric": "revenue"}, raise_on_error=False
        )
        assert result.is_error
