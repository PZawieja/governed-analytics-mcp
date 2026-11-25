import os
import subprocess

import psycopg
import pytest

from governed_analytics_mcp import config
from governed_analytics_mcp.metrics import load_catalog


@pytest.fixture(scope="session")
def catalog():
    if not config.MANIFEST_PATH.exists() or not config.DUCKDB_PATH.exists():
        subprocess.run(
            ["dbt", "build", "--profiles-dir", "."], cwd=config.DBT_DIR, check=True
        )
    return load_catalog(config.METRICS_PATH, config.MANIFEST_PATH)


def _pg_ready() -> bool:
    try:
        with psycopg.connect(config.GATEWAY_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def pg(catalog):
    if not _pg_ready():
        if os.environ.get("GAMCP_REQUIRE_PG"):
            pytest.fail("Postgres is required (GAMCP_REQUIRE_PG) but unreachable")
        pytest.skip("Postgres not running: docker compose up -d && load_pg.py")
    return config.GATEWAY_URL
