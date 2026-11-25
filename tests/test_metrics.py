import copy
import json

import pytest

from governed_analytics_mcp import config
from governed_analytics_mcp.metrics import (
    CatalogError,
    load_catalog,
    mart_nodes,
    validate_manifest,
)


@pytest.fixture
def manifest(catalog):
    return json.loads(config.MANIFEST_PATH.read_text())


def test_repo_manifest_is_valid(manifest):
    assert validate_manifest(manifest) == []


def test_mart_without_access_meta_fails(manifest):
    broken = copy.deepcopy(manifest)
    node = next(n for n in mart_nodes(broken).values() if n["name"] == "dim_stores")
    node["meta"] = {}
    node["config"]["meta"] = {}
    errors = validate_manifest(broken)
    assert any("dim_stores" in e for e in errors)


def test_policy_column_must_exist(manifest):
    broken = copy.deepcopy(manifest)
    node = next(n for n in mart_nodes(broken).values() if n["name"] == "dim_stores")
    node["config"]["meta"] = {"policy_column": "territory"}
    node["meta"] = {"policy_column": "territory"}
    assert any("territory" in e for e in validate_manifest(broken))


def test_hidden_model_cannot_back_a_metric(tmp_path, catalog):
    metrics = tmp_path / "metrics.yml"
    metrics.write_text(
        "models:\n"
        "  dim_region_access:\n"
        "    time_column: region\n"
        "    dimensions: {user: user_name}\n"
        "metrics:\n"
        "  grants: {model: dim_region_access, expr: COUNT(*)}\n"
    )
    with pytest.raises(CatalogError, match="hidden"):
        load_catalog(metrics, config.MANIFEST_PATH)


def test_catalog_records_access(catalog):
    assert catalog.metrics["revenue"].model.policy_column == "region"
    assert catalog.metrics["company_revenue"].model.agent_access == "all_regions_only"
    assert catalog.models["fct_store_sales"].relation == "fct_store_sales"
