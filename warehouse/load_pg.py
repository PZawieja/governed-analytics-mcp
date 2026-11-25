import argparse
from pathlib import Path

import duckdb
import psycopg

from governed_analytics_mcp import config

HERE = Path(__file__).parent


def bootstrap(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute((HERE / "bootstrap.sql").read_text())


def copy_marts(duckdb_path: Path, transformer_url: str) -> list[str]:
    with psycopg.connect(transformer_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS marts CASCADE")
        conn.execute("CREATE SCHEMA marts")

    con = duckdb.connect()
    con.execute("INSTALL postgres")
    con.execute("LOAD postgres")
    con.execute(f"ATTACH '{duckdb_path}' AS dbt (READ_ONLY)")
    con.execute(f"ATTACH '{transformer_url}' AS pg (TYPE postgres)")
    tables = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = 'dbt' AND table_schema = 'marts' "
            "ORDER BY table_name"
        ).fetchall()
    ]
    for table in tables:
        con.execute(
            f'CREATE TABLE pg.marts."{table}" AS SELECT * FROM dbt.marts."{table}"'
        )
    con.close()
    return tables


def apply_policies(transformer_url: str) -> None:
    with psycopg.connect(transformer_url, autocommit=True) as conn:
        conn.execute((HERE / "policies.sql").read_text())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy the dbt marts into Postgres as transformer, then apply RLS."
    )
    parser.add_argument("--duckdb", type=Path, default=config.DUCKDB_PATH)
    parser.add_argument("--skip-bootstrap", action="store_true")
    args = parser.parse_args()

    if not args.skip_bootstrap:
        bootstrap(config.ADMIN_URL)
    tables = copy_marts(args.duckdb, config.TRANSFORMER_URL)
    apply_policies(config.TRANSFORMER_URL)
    print(f"loaded marts.{', marts.'.join(tables)} and applied policies")


if __name__ == "__main__":
    main()
