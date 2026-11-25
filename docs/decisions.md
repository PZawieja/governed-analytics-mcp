# Decisions

## Postgres RLS as the main backend, DuckDB as a labeled fallback

The post's claim is that the warehouse, not agent code, should decide what the asker sees. DuckDB, the default for the rest of this series, has no row-level security, so any scoping on DuckDB has to happen in the server. That would make the companion repo do the thing the post warns against. Postgres 16 has RLS, grants and `security_invoker` views, and the post's demo ran on it.

dbt still builds in DuckDB (fast, no infrastructure, same as the series). `load_pg.py` copies the marts into Postgres as `transformer`, the owner, and `policies.sql` applies the policies. The DuckDB backend stays for running without Docker, appends `region IN (SELECT ... WHERE user_name = ?)` itself, and says so in `explain_last_query` (`enforcement: app-code filter`).

## `SET LOCAL ROLE` stands in for a per-asker warehouse token

In Snowflake or Databricks, the server would exchange the user's token for one issued to the warehouse for that user (External OAuth, or RFC 8693 token exchange through the IdP), and the warehouse would map it to the user and role. Postgres has no equivalent, so the closest honest stand-in is:

- `agent_gateway` logs in, owns nothing, and is `NOINHERIT`. Its persona memberships are granted `WITH INHERIT FALSE, SET TRUE`, so it can read nothing until it switches.
- Each tool call is one transaction: `SET TRANSACTION READ ONLY`, `SET LOCAL statement_timeout`, `SET LOCAL ROLE <asker>`. The role resets at commit or rollback, so a later call can't inherit it.
- The gateway is not a member of `transformer` or any role with `BYPASSRLS`, so even a bug in the server can't pick the owner. A test asserts that `SET ROLE transformer` fails.

What this doesn't give you: the warehouse never sees proof that the person authenticated. The gateway is trusted to switch to the right role. A real token per asker removes that trust, so use it where the warehouse supports it.

## No raw SQL

The agent picks a metric, dimensions, filters and dates. Identifiers come only from `metrics.yml` (checked against the dbt manifest at startup), and values are bind parameters. That removes SQL injection and "SELECT * FROM region_access" as a class of problem. It also keeps the generated SQL stable, which makes the cache and the audit log's `sql_hash` meaningful.

The trade-off is reach: the agent can't answer anything the catalog doesn't define. For a governed surface that's intended.

## The cache key includes the asker

With RLS, every asker sends the same SQL text and the warehouse returns different rows. A cache keyed by question or SQL alone returns whoever asked first's rows. The eval runs Jake's query first on purpose, and `--cache-keyed-by sql_only` leaks on exactly the three personas who follow him.

On the DuckDB backend the asker's name is a bind parameter in the filter, so even a SQL-only key happens not to collide there. Don't rely on that: RLS-backed setups have no such parameter.

Keyed by user, not role, because `region_access` looks up individuals. If every policy were role-based, keying by role would get more hits.

## Summary tables: `all_regions_only` instead of dropping them

`fct_company_monthly_total` was built from every row and has no region column left, so no row policy can scope it. Options considered:

1. Drop it. That loses a useful table for finance.
2. Rebuild it per region. That's just `fct_store_sales` again.
3. Keep it and grant it only to people who may see every region.

We chose 3. Postgres denies everyone else, and the server turns the permission error into "not available for your access". Every mart must declare `meta.policy_column` or `meta.agent_access` (`all_regions_only` | `hidden`), and `gamcp check` fails CI otherwise. That forces the decision for each new table.

## Evals use an independent oracle

`eval/cases.yml` writes down each persona's grants. The oracle computes the expected answer from those grants on an admin DuckDB connection, without reading `region_access` or using the server's enforcement, so it can't share their bugs. Then:

- a leak is a row outside the grant, a number larger than the grant allows, or rows where a denial was expected;
- wrong is any other mismatch.

A few cases also pin the post's figures ($680,000; $2.70M) so a data change that breaks the story fails loudly.

Agent-level evals score the model's prose. An answer leaks if it mentions a figure only someone with more grants could know, including the remainder after subtracting the asker's own total, which is the post's subtraction attack. Number matching is vendored from `llmops-eval-harness`, with short forms like `$1.15M` added.

## No-key and fork modes

Everything except `gamcp ask` and `gamcp eval --agent` runs without an Anthropic key. CI runs the agent evals only when the `ANTHROPIC_API_KEY` secret exists, so forks and the default setup still run the deterministic 0-leak gate.

## Why not wrap an existing server

The dbt MCP server and Cube's MCP server are broader and production-grade. This repo is a reference for one idea, and it needed the identity to reach the database role with nothing in between that could widen it. Wrapping another server would hide exactly the part the post is about.
