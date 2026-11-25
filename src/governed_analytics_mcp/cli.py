import argparse
import asyncio
import calendar
import json
import os
import sys

from governed_analytics_mcp import config


def _month_range(month: str) -> tuple[str, str]:
    year, mon = (int(p) for p in month.split("-"))
    return (
        f"{year:04d}-{mon:02d}-01",
        f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}",
    )


def _filters(pairs: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for pair in pairs:
        dim, _, value = pair.partition("=")
        out.setdefault(dim, []).append(value)
    return out


def cmd_check(_args) -> int:
    from governed_analytics_mcp.metrics import CatalogError, load_catalog

    try:
        catalog = load_catalog(config.METRICS_PATH, config.MANIFEST_PATH)
    except CatalogError as exc:
        print(f"catalog check failed:\n{exc}", file=sys.stderr)
        return 1
    print(
        f"ok: {len(catalog.metrics)} metrics on {len(catalog.models)} governed models"
    )
    return 0


def cmd_mint_token(args) -> int:
    from governed_analytics_mcp.identity import mint_token

    print(mint_token(args.user, expires_in=args.expires_in))
    return 0


def cmd_serve(args) -> int:
    from governed_analytics_mcp.app import make_service
    from governed_analytics_mcp.identity import verify_token
    from governed_analytics_mcp.server import build_server, jwt_verifier

    service = make_service(args.backend)
    if args.transport == "stdio":
        token = args.token or os.environ.get("GAMCP_TOKEN")
        if not token:
            print("stdio needs --token or GAMCP_TOKEN", file=sys.stderr)
            return 2
        server = build_server(service, bound_asker=verify_token(token))
        server.run(transport="stdio", show_banner=False)
    else:
        server = build_server(service, verifier=jwt_verifier())
        server.run(transport="http", host=args.host, port=args.port)
    return 0


def _tool_args(args) -> tuple[str, dict]:
    if args.tool == "query_metric":
        payload: dict = {"metric": args.metric}
        if args.by:
            payload["group_by"] = args.by
        if args.filter:
            payload["filters"] = _filters(args.filter)
        if args.month:
            payload["start"], payload["end"] = _month_range(args.month)
        if args.start:
            payload["start"] = args.start
        if args.end:
            payload["end"] = args.end
        return "query_metric", payload
    if args.tool == "describe_metric":
        return "describe_metric", {"metric": args.metric}
    return args.tool, {}


async def _call(args) -> int:
    from fastmcp import Client

    from governed_analytics_mcp.identity import asker_for_subject, mint_token

    if args.url:
        client = Client(args.url, auth=args.token or mint_token(args.as_user))
    else:
        from governed_analytics_mcp.app import make_service
        from governed_analytics_mcp.server import build_server

        service = make_service(args.backend, cache_keyed_by=args.cache_keyed_by)
        client = Client(
            build_server(service, bound_asker=asker_for_subject(args.as_user))
        )

    name, payload = _tool_args(args)
    async with client:
        result = await client.call_tool(name, payload)
        out = {"tool": name, "as": args.as_user, "result": result.structured_content}
        if args.explain:
            explained = await client.call_tool("explain_last_query", {})
            out["explain"] = explained.structured_content
    print(json.dumps(out, indent=2))
    return 0


def cmd_call(args) -> int:
    return asyncio.run(_call(args))


def cmd_eval(args) -> int:
    from governed_analytics_mcp.app import make_service
    from governed_analytics_mcp.evals import (
        format_report,
        gate,
        load_cases,
        run_tool_evals,
    )

    cases = load_cases()
    failed = False
    for backend in args.backend:
        service = make_service(backend, cache_keyed_by=args.cache_keyed_by)
        results = run_tool_evals(service, cases)
        verdict = gate(results)
        print(
            format_report(f"{backend} (cache keyed by {args.cache_keyed_by})", results)
        )
        print(
            "  gate: "
            + (
                "PASS"
                if verdict["passed"]
                else "FAIL: " + "; ".join(verdict["reasons"])
            )
        )
        failed |= not verdict["passed"]

    if args.agent:
        from governed_analytics_mcp.agent import run_agent_evals

        failed |= not asyncio.run(run_agent_evals(args.backend[0], cases))
    return 1 if failed else 0


def cmd_ask(args) -> int:
    from governed_analytics_mcp.agent import ask

    answer = asyncio.run(ask(args.as_user, args.question, args.backend, verbose=True))
    print(answer)
    return 0


def main(argv: list[str] | None = None) -> int:
    from governed_analytics_mcp.app import BACKENDS

    parser = argparse.ArgumentParser(prog="gamcp", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="validate metrics.yml against the dbt manifest")

    p = sub.add_parser("mint-token", help="mint a demo bearer token for a persona")
    p.add_argument("user")
    p.add_argument("--expires-in", type=int, default=8 * 3600)

    p = sub.add_parser("serve", help="run the MCP server")
    p.add_argument("--transport", choices=["http", "stdio"], default="http")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--backend", choices=BACKENDS, default="postgres")
    p.add_argument("--token", help="stdio only: the asker's token")

    p = sub.add_parser("call", help="call one tool as a persona, no LLM involved")
    p.add_argument("--as", dest="as_user", required=True)
    p.add_argument("tool", choices=["list_metrics", "describe_metric", "query_metric"])
    p.add_argument("metric", nargs="?")
    p.add_argument("--by", action="append", help="group by a dimension (repeatable)")
    p.add_argument("--filter", action="append", help="dim=value (repeatable)")
    p.add_argument("--month", help="YYYY-MM, sets start and end")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument(
        "--explain", action="store_true", help="also show explain_last_query"
    )
    p.add_argument("--backend", choices=BACKENDS, default="postgres")
    p.add_argument("--cache-keyed-by", choices=["asker", "sql_only"], default="asker")
    p.add_argument("--url", help="call a running HTTP server instead of in-process")
    p.add_argument("--token", help="with --url: bearer token (default: mint one)")

    p = sub.add_parser("eval", help="run the persona evals; exits 1 on any leak")
    p.add_argument("--backend", choices=BACKENDS, action="append")
    p.add_argument("--cache-keyed-by", choices=["asker", "sql_only"], default="asker")
    p.add_argument("--agent", action="store_true", help="also run agent-level evals")

    p = sub.add_parser("ask", help="ask a question through Claude as a persona")
    p.add_argument("--as", dest="as_user", required=True)
    p.add_argument("question")
    p.add_argument("--backend", choices=BACKENDS, default="postgres")

    args = parser.parse_args(argv)
    if args.command == "eval" and not args.backend:
        args.backend = ["postgres", "duckdb"]
    handler = {
        "check": cmd_check,
        "mint-token": cmd_mint_token,
        "serve": cmd_serve,
        "call": cmd_call,
        "eval": cmd_eval,
        "ask": cmd_ask,
    }[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
