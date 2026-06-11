"""Dataset-scoped semantic catalog loading."""



import json
from pathlib import Path

from .schemas import SemanticCatalog, SemanticCatalogSummary, ValidateRequest


DEFAULT_SEMANTIC_DIR = Path(__file__).resolve().parents[2] / "resources" / "semantic"


def _resolve_semantic_dir(base_dir: str | Path | None = None) -> Path:
    # [CUSTOM] 统一语义目录根路径解析，避免 API 与服务层各自拼路径。
    return Path(base_dir) if base_dir is not None else DEFAULT_SEMANTIC_DIR


def _ensure_formal_catalog_payload(payload: dict) -> None:
    # [CUSTOM] 重构后不再兼容旧的平铺 table 结构，提前给出明确错误信息，
    # 避免调用方只看到一串字段缺失。
    if "catalog_version" in payload and "tables" in payload:
        return

    has_legacy_table_fields = any("table" in item for item in payload.get("metrics", [])) or any(
        "table" in item for item in payload.get("dimensions", [])
    )
    if has_legacy_table_fields or "tables" not in payload or "catalog_version" not in payload:
        raise ValueError(
            "只支持新版语义目录结构: 必须包含 catalog_version/tables，"
            "metrics 和 dimensions 必须使用 table_key 引用语义表"
        )


def load_semantic_catalog(
    dataset_id: str, base_dir: str | Path | None = None
) -> SemanticCatalog:
    """Load a semantic catalog JSON file for a dataset."""
    semantic_dir = _resolve_semantic_dir(base_dir)
    catalog_path = semantic_dir / f"{dataset_id}.json"
    if not catalog_path.exists():
        raise FileNotFoundError(f"未找到数据集语义目录: {catalog_path}")

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if "dataset_id" not in payload or not payload["dataset_id"]:
        payload["dataset_id"] = dataset_id
    _ensure_formal_catalog_payload(payload)

    catalog = ValidateRequest.parse(SemanticCatalog, payload)
    if catalog.dataset_id != dataset_id:
        raise ValueError(
            f"语义目录 dataset_id 不匹配: expected={dataset_id}, actual={catalog.dataset_id}"
        )

    return catalog


def summarize_semantic_catalog(catalog: SemanticCatalog) -> SemanticCatalogSummary:
    """Return a compact summary for a semantic catalog."""
    # [CUSTOM] 目录观测接口只暴露摘要，避免把完整业务配置直接透给前端。
    return ValidateRequest.parse(
        SemanticCatalogSummary,
        {
            "catalog_version": catalog.catalog_version,
            "dataset_id": catalog.dataset_id,
            "table_count": len(catalog.tables),
            "metric_count": len(catalog.metrics),
            "dimension_count": len(catalog.dimensions),
            "alias_count": len(catalog.aliases),
            "metric_version_count": len(catalog.metric_versions),
        },
    )


def list_semantic_catalogs(
    base_dir: str | Path | None = None,
) -> list[SemanticCatalogSummary]:
    """List available semantic catalog summaries under the configured directory."""
    # [CUSTOM] 提供目录发现能力，便于新语义链路做数据集可观测与健康检查。
    semantic_dir = _resolve_semantic_dir(base_dir)
    if not semantic_dir.exists():
        return []

    summaries: list[SemanticCatalogSummary] = []
    for catalog_path in sorted(semantic_dir.glob("*.json")):
        catalog = load_semantic_catalog(catalog_path.stem, base_dir=semantic_dir)
        summaries.append(summarize_semantic_catalog(catalog))

    return summaries
