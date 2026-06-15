#!/usr/bin/env python
"""Download UCI Online Retail data and run controlled QSQL smoke checks."""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

SOURCE_PAGE_URL = "https://archive.ics.uci.edu/dataset/352/online%2Bretail"
DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
DATASET_ID = "online_retail"
TABLE_NAME = "online_retail_orders"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "resources" / "uploads" / DATASET_ID
XLSX_NAME = "Online Retail.xlsx"
CSV_NAME = "Online Retail.csv"
SQLITE_NAME = "online_retail.sqlite3"
DATE_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%y %H:%M:%S",
    "%m/%d/%y %H:%M",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)

if str(REPO_ROOT) not in sys.path:
    # [CUSTOM] 支持 `python scripts/real_business_online_retail_smoke.py` 直接运行。
    sys.path.insert(0, str(REPO_ROOT))

from src.qsql.schemas import SemanticFilter, SemanticQueryDraft, SemanticTimeRange  # noqa: E402
from src.qsql.semantic_catalog import load_semantic_catalog  # noqa: E402
from src.qsql.sql_builder import build_query_execution_plan  # noqa: E402


def _stream_download(url: str, target_path: Path, *, trust_env: bool) -> None:
    session = requests.Session()
    session.trust_env = trust_env
    with session.get(url, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        with target_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def _download_dataset(zip_path: Path) -> None:
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = zip_path.with_suffix(".zip.tmp")
    print(f"[download] source={SOURCE_PAGE_URL}")
    print(f"[download] url={DOWNLOAD_URL}")
    try:
        _stream_download(DOWNLOAD_URL, tmp_path, trust_env=True)
    except requests.RequestException as exc:
        print(f"[download] 代理下载失败，改为直连重试: {exc}")
        _stream_download(DOWNLOAD_URL, tmp_path, trust_env=False)
    tmp_path.replace(zip_path)


def _extract_xlsx(zip_path: Path, xlsx_path: Path) -> None:
    if xlsx_path.exists() and xlsx_path.stat().st_size > 0:
        return

    with zipfile.ZipFile(zip_path) as archive:
        member = next(
            item for item in archive.namelist() if item.endswith(XLSX_NAME)
        )
        archive.extract(member, path=xlsx_path.parent)
        extracted_path = xlsx_path.parent / member
        if extracted_path != xlsx_path:
            extracted_path.replace(xlsx_path)


def _convert_xlsx_to_csv(xlsx_path: Path, csv_path: Path, *, force: bool) -> None:
    if csv_path.exists() and csv_path.stat().st_size > 0 and not force:
        return

    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if libreoffice is None:
        raise RuntimeError(
            "未找到 libreoffice/soffice，无法把 UCI xlsx 转 CSV；"
            "请安装 LibreOffice，或手动把 Online Retail.xlsx 保存为 CSV。"
        )

    if csv_path.exists():
        csv_path.unlink()

    # [CUSTOM] 真实数据 smoke 不引入 openpyxl 运行依赖，优先复用系统 LibreOffice 转换。
    subprocess.run(
        [
            libreoffice,
            "--headless",
            "--convert-to",
            "csv",
            "--outdir",
            str(csv_path.parent),
            str(xlsx_path),
        ],
        check=True,
        cwd=csv_path.parent,
    )
    if not csv_path.exists():
        raise RuntimeError(f"LibreOffice 转换未生成 CSV: {csv_path}")


def _database_row_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as connection:
        try:
            row = connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()
        except sqlite3.Error:
            return 0
    return int(row[0]) if row else 0


def _parse_datetime(value: str) -> datetime:
    text = value.strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"无法解析 InvoiceDate: {value!r}") from exc


def _to_int(value: str) -> int:
    return int(float(value.strip()))


def _to_float(value: str) -> float:
    return float(value.strip())


def _clean_customer_id(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith(".0"):
        return text[:-2]
    return text


def _normalise_row(row: dict[str, str]) -> tuple[Any, ...]:
    invoice_no = row["InvoiceNo"].strip()
    stock_code = row["StockCode"].strip()
    description = row["Description"].strip()
    quantity = _to_int(row["Quantity"])
    invoice_datetime = _parse_datetime(row["InvoiceDate"])
    unit_price = _to_float(row["UnitPrice"])
    customer_id = _clean_customer_id(row.get("CustomerID", ""))
    country = row["Country"].strip()
    revenue = round(quantity * unit_price, 4)
    is_cancellation = 1 if invoice_no.upper().startswith("C") else 0

    return (
        invoice_no,
        stock_code,
        description,
        quantity,
        invoice_datetime.isoformat(sep=" "),
        invoice_datetime.date().isoformat(),
        invoice_datetime.strftime("%Y-%m"),
        unit_price,
        customer_id,
        country,
        revenue,
        is_cancellation,
    )


def _import_csv_to_sqlite(csv_path: Path, db_path: Path, *, force: bool) -> int:
    existing_rows = _database_row_count(db_path)
    if existing_rows > 0 and not force:
        return existing_rows

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        connection.execute(
            f"""
            CREATE TABLE {TABLE_NAME} (
                invoice_no TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                description TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                invoice_datetime TEXT NOT NULL,
                invoice_date TEXT NOT NULL,
                invoice_month TEXT NOT NULL,
                unit_price REAL NOT NULL,
                customer_id TEXT,
                country TEXT NOT NULL,
                revenue REAL NOT NULL,
                is_cancellation INTEGER NOT NULL
            )
            """
        )

        insert_sql = f"""
            INSERT INTO {TABLE_NAME} (
                invoice_no, stock_code, description, quantity,
                invoice_datetime, invoice_date, invoice_month, unit_price,
                customer_id, country, revenue, is_cancellation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        inserted = 0
        skipped = 0
        batch: list[tuple[Any, ...]] = []
        csv.field_size_limit(sys.maxsize)
        with csv_path.open("r", encoding="cp1252", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    batch.append(_normalise_row(row))
                except (KeyError, ValueError) as exc:
                    skipped += 1
                    if skipped <= 5:
                        print(f"[import] 跳过异常行: {exc}")
                    continue
                if len(batch) >= 5000:
                    connection.executemany(insert_sql, batch)
                    inserted += len(batch)
                    batch.clear()
            if batch:
                connection.executemany(insert_sql, batch)
                inserted += len(batch)

        connection.execute(
            f"CREATE INDEX idx_{TABLE_NAME}_invoice_date ON {TABLE_NAME}(invoice_date)"
        )
        connection.execute(
            f"CREATE INDEX idx_{TABLE_NAME}_invoice_month ON {TABLE_NAME}(invoice_month)"
        )
        connection.execute(
            f"CREATE INDEX idx_{TABLE_NAME}_country ON {TABLE_NAME}(country)"
        )
        connection.commit()

    print(f"[import] inserted={inserted} skipped={skipped} db={db_path}")
    return inserted


def _query_cases() -> list[tuple[str, SemanticQueryDraft]]:
    # [CUSTOM] 用真实零售交易表覆盖受控 SQL 生成的典型业务问题。
    return [
        (
            "2011 年各国家有效销售额",
            SemanticQueryDraft(
                analysis_type="group_by",
                metric_key="revenue",
                group_by_dimension_keys=["country"],
                filters=[],
                time_range=SemanticTimeRange(
                    dimension_key="invoice_date",
                    start="2011-01-01",
                    end="2011-12-31",
                ),
                metric_version_key="valid_revenue",
            ),
        ),
        (
            "2011 年英国每月有效销售额",
            SemanticQueryDraft(
                analysis_type="trend",
                metric_key="revenue",
                group_by_dimension_keys=["invoice_month"],
                filters=[
                    SemanticFilter(
                        dimension_key="country",
                        operator="eq",
                        value="United Kingdom",
                    )
                ],
                time_range=SemanticTimeRange(
                    dimension_key="invoice_date",
                    start="2011-01-01",
                    end="2011-12-31",
                ),
                metric_version_key="valid_revenue",
            ),
        ),
        (
            "2011 年各国家有效发票数",
            SemanticQueryDraft(
                analysis_type="group_by",
                metric_key="invoice_count",
                group_by_dimension_keys=["country"],
                filters=[],
                time_range=SemanticTimeRange(
                    dimension_key="invoice_date",
                    start="2011-01-01",
                    end="2011-12-31",
                ),
                metric_version_key="valid_invoice_count",
            ),
        ),
    ]


def _sample_result_rows(
    connection: sqlite3.Connection,
    sql: str,
    *,
    grouped: bool,
    limit: int,
) -> list[dict[str, Any]]:
    if grouped:
        sample_sql = f"SELECT * FROM ({sql}) ORDER BY metric_value DESC LIMIT ?"
        cursor = connection.execute(sample_sql, (limit,))
    else:
        cursor = connection.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def _run_smoke_queries(db_path: Path, *, row_limit: int) -> None:
    catalog = load_semantic_catalog(DATASET_ID)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        for label, draft in _query_cases():
            plan = build_query_execution_plan(catalog=catalog, semantic_query=draft)
            rows = _sample_result_rows(
                connection,
                plan.sql,
                grouped=bool(plan.group_by_dimension_keys),
                limit=row_limit,
            )
            if not rows:
                raise RuntimeError(f"真实数据查询无结果: {label}")
            if rows[0].get("metric_value") is None:
                raise RuntimeError(f"真实数据查询指标为空: {label}")
            print(f"\n[query] {label}")
            print(f"[sql] {plan.sql}")
            print(f"[rows] sample={rows}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下载 UCI Online Retail 真实交易数据并运行 QSQL 受控 SQL smoke"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="数据缓存目录，默认 resources/uploads/online_retail",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="重新转换 CSV 并重建 SQLite 测试库",
    )
    parser.add_argument("--row-limit", type=int, default=5, help="每个查询展示行数")
    args = parser.parse_args()

    data_dir = args.data_dir
    zip_path = data_dir / "online_retail.zip"
    xlsx_path = data_dir / XLSX_NAME
    csv_path = data_dir / CSV_NAME
    db_path = data_dir / SQLITE_NAME

    _download_dataset(zip_path)
    _extract_xlsx(zip_path, xlsx_path)
    _convert_xlsx_to_csv(xlsx_path, csv_path, force=args.force_refresh)
    rows = _import_csv_to_sqlite(csv_path, db_path, force=args.force_refresh)
    print(f"[dataset] dataset_id={DATASET_ID} rows={rows} sqlite={db_path}")
    _run_smoke_queries(db_path, row_limit=args.row_limit)


if __name__ == "__main__":
    main()
