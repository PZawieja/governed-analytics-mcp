import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ALL_REGIONS_ONLY = "all_regions_only"
HIDDEN = "hidden"


@dataclass(frozen=True)
class Model:
    name: str
    schema: str
    relation: str
    time_column: str
    dimensions: dict[str, str]
    policy_column: str | None = None
    agent_access: str | None = None

    @property
    def qualified(self) -> str:
        return f'"{self.schema}"."{self.relation}"'


@dataclass(frozen=True)
class Metric:
    name: str
    model: Model
    expr: str
    description: str


@dataclass
class Catalog:
    metrics: dict[str, Metric]
    models: dict[str, Model] = field(default_factory=dict)


class CatalogError(ValueError):
    pass


def _node_meta(node: dict) -> dict:
    return {**node.get("meta", {}), **node.get("config", {}).get("meta", {})}


def mart_nodes(manifest: dict) -> dict[str, dict]:
    return {
        n["name"]: n
        for n in manifest["nodes"].values()
        if n["resource_type"] == "model" and n["schema"] == "marts"
    }


def validate_manifest(manifest: dict) -> list[str]:
    errors = []
    for name, node in sorted(mart_nodes(manifest).items()):
        meta = _node_meta(node)
        policy = meta.get("policy_column")
        access = meta.get("agent_access")
        if policy and access:
            errors.append(f"{name}: set policy_column or agent_access, not both")
        elif policy:
            if policy not in node.get("columns", {}):
                errors.append(
                    f"{name}: policy_column {policy!r} is not a documented column"
                )
        elif access not in (ALL_REGIONS_ONLY, HIDDEN):
            errors.append(
                f"{name}: marts must declare meta.policy_column or "
                f"meta.agent_access ({ALL_REGIONS_ONLY} | {HIDDEN})"
            )
    return errors


def load_catalog(metrics_path: Path, manifest_path: Path) -> Catalog:
    spec = yaml.safe_load(metrics_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    errors = validate_manifest(manifest)
    marts = mart_nodes(manifest)

    models: dict[str, Model] = {}
    for name, cfg in spec["models"].items():
        node = marts.get(name)
        if node is None:
            errors.append(f"metrics.yml: model {name} is not a mart in the manifest")
            continue
        meta = _node_meta(node)
        if meta.get("agent_access") == HIDDEN:
            errors.append(f"metrics.yml: {name} is hidden from agents")
            continue
        columns = set(node.get("columns", {}))
        for col in [cfg["time_column"], *cfg["dimensions"].values()]:
            if col not in columns:
                errors.append(f"metrics.yml: {name}.{col} is not a documented column")
        models[name] = Model(
            name=name,
            schema=node["schema"],
            relation=node.get("alias") or name,
            time_column=cfg["time_column"],
            dimensions=dict(cfg["dimensions"]),
            policy_column=meta.get("policy_column"),
            agent_access=meta.get("agent_access"),
        )

    metrics = {}
    for name, cfg in spec["metrics"].items():
        model = models.get(cfg["model"])
        if model is None:
            errors.append(
                f"metrics.yml: metric {name} uses unknown model {cfg['model']}"
            )
            continue
        metrics[name] = Metric(
            name=name,
            model=model,
            expr=cfg["expr"],
            description=" ".join(cfg.get("description", "").split()),
        )

    if errors:
        raise CatalogError("\n".join(errors))
    return Catalog(metrics=metrics, models=models)
