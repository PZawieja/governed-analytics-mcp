import os
from pathlib import Path

ROOT = Path(os.environ.get("GAMCP_ROOT", Path(__file__).resolve().parents[2]))
DBT_DIR = ROOT / "warehouse" / "dbt"
DUCKDB_PATH = Path(
    os.environ.get("GAMCP_DUCKDB_PATH", DBT_DIR / "copper_kettle.duckdb")
)
MANIFEST_PATH = DBT_DIR / "target" / "manifest.json"
METRICS_PATH = ROOT / "metrics.yml"
CASES_PATH = ROOT / "eval" / "cases.yml"
AUDIT_PATH = Path(
    os.environ.get("GAMCP_AUDIT_PATH", ROOT / "audit" / "audit_log.jsonl")
)
KEYS_DIR = Path(os.environ.get("GAMCP_KEYS_DIR", ROOT / ".keys"))

PG_HOST = os.environ.get("GAMCP_PG_HOST", "localhost")
PG_PORT = os.environ.get("GAMCP_PG_PORT", "54329")
PG_DB = os.environ.get("GAMCP_PG_DB", "copper_kettle")


def pg_url(user: str, password: str | None = None) -> str:
    password = password or os.environ.get(f"GAMCP_PG_{user.upper()}_PASSWORD", user)
    return f"postgresql://{user}:{password}@{PG_HOST}:{PG_PORT}/{PG_DB}"


ADMIN_URL = os.environ.get(
    "GAMCP_PG_ADMIN_URL", pg_url("postgres", os.environ.get("PGPASSWORD", "postgres"))
)
TRANSFORMER_URL = pg_url("transformer")
GATEWAY_URL = pg_url("agent_gateway")

TOKEN_ISSUER = "https://copper-kettle.example/idp"
TOKEN_AUDIENCE = "governed-analytics-mcp"
