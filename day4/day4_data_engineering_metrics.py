#!/usr/bin/env python
# coding: utf-8

"""Clean library datasets and produce Power BI-ready engineering metrics.

The pipeline creates two clean CSV files and appends one audit row for every
load, validation, transformation and save step to:

    Clean_Data/data_engineering_metrics.csv

Each execution has a unique run_id, allowing Power BI to show both the latest
run and historical trends.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import pandas as pd


BASE_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_CLEAN_DATA_DIRECTORY = BASE_DIRECTORY / "Clean_Data"
DEFAULT_METRICS_PATH = DEFAULT_CLEAN_DATA_DIRECTORY / "data_engineering_metrics.csv"

METRICS_COLUMNS = [
    "run_id",
    "run_timestamp_utc",
    "pipeline_name",
    "dataset",
    "step_number",
    "step_name",
    "status",
    "rows_before",
    "rows_after",
    "rows_added",
    "rows_removed",
    "columns_before",
    "columns_after",
    "columns_added",
    "columns_removed",
    "columns_added_names",
    "columns_removed_names",
    "missing_values_before",
    "missing_values_after",
    "missing_values_removed",
    "duplicate_rows_before",
    "duplicate_rows_after",
    "duplicate_rows_removed",
    "completeness_before_pct",
    "completeness_after_pct",
    "uniqueness_before_pct",
    "uniqueness_after_pct",
    "changed_cells",
    "quality_issue_count",
    "invalid_date_rows",
    "late_return_rows",
    "missing_key_rows",
    "blank_required_text_rows",
    "duplicate_key_rows",
    "processing_time_ms",
    "source_file",
    "output_file",
    "details",
]


def utc_timestamp() -> str:
    """Return a Power BI-friendly UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise_column_names(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with lowercase snake_case column names."""
    cleaned = dataframe.copy()
    cleaned.columns = (
        cleaned.columns.astype("string")
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return cleaned


def add_days_between(
    dataframe: pd.DataFrame,
    start_date_column: str,
    end_date_column: str,
    output_column: str = "days_between",
) -> pd.DataFrame:
    """Enrich a DataFrame with the difference between two dates."""
    enriched = dataframe.copy()

    def parse_library_date(series: pd.Series) -> pd.Series:
        date_text = (
            series.astype("string")
            .str.strip()
            .str.strip('"')
            .str.strip("'")
            .str.strip()
        )
        parsed = pd.to_datetime(date_text, format="%d/%m/%Y", errors="coerce")
        unresolved = parsed.isna() & date_text.notna()
        if unresolved.any():
            parsed.loc[unresolved] = pd.to_datetime(
                date_text.loc[unresolved], format="%Y-%m-%d", errors="coerce"
            )
        return parsed

    start_dates = parse_library_date(enriched[start_date_column])
    end_dates = parse_library_date(enriched[end_date_column])
    enriched[start_date_column] = start_dates
    enriched[end_date_column] = end_dates
    enriched[output_column] = (end_dates - start_dates).dt.days.astype("Int64")
    return enriched


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: Iterable[str],
    dataset_name: str,
) -> pd.DataFrame:
    """Raise a clear error when an input dataset is missing required columns."""
    missing_columns = set(required_columns).difference(dataframe.columns)
    if missing_columns:
        raise ValueError(
            f"{dataset_name} file is missing columns: {sorted(missing_columns)}"
        )
    return dataframe.copy()


def strip_text_columns(
    dataframe: pd.DataFrame,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Remove leading and trailing spaces from selected text columns."""
    cleaned = dataframe.copy()
    for column in columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
    return cleaned


def convert_to_nullable_integer(
    dataframe: pd.DataFrame,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Convert selected columns to pandas nullable integer values."""
    cleaned = dataframe.copy()
    for column in columns:
        cleaned[column] = pd.to_numeric(
            cleaned[column], errors="coerce"
        ).astype("Int64")
    return cleaned


def add_book_quality_flags(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add late-return and invalid-date flags to the books dataset."""
    enriched = dataframe.copy()

    if "days_allowed_to_borrow" in enriched.columns:
        allowance_text = (
            enriched["days_allowed_to_borrow"].astype("string").str.strip().str.lower()
        )
        parts = allowance_text.str.extract(
            r"(?P<number>\d+)\s*(?P<unit>weeks?|days?)"
        )
        number = pd.to_numeric(parts["number"], errors="coerce").astype("Int64")
        days_allowed = pd.Series(pd.NA, index=enriched.index, dtype="Int64")
        week_rows = parts["unit"].str.startswith("week", na=False)
        day_rows = parts["unit"].str.startswith("day", na=False)
        days_allowed.loc[week_rows] = number.loc[week_rows] * 7
        days_allowed.loc[day_rows] = number.loc[day_rows]
        enriched["days_allowed"] = days_allowed
    elif "days_allowed" in enriched.columns:
        enriched["days_allowed"] = pd.to_numeric(
            enriched["days_allowed"], errors="coerce"
        ).astype("Int64")

    if "days_allowed" in enriched.columns:
        enriched["returned_late"] = (
            enriched["loan_days"] > enriched["days_allowed"]
        ).astype("boolean")
    enriched["invalid_date_order"] = enriched["loan_days"].lt(0).astype("boolean")
    return enriched


def remove_duplicate_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove complete duplicate rows and reset the index."""
    return dataframe.drop_duplicates().reset_index(drop=True)


def remove_empty_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove rows where every value is missing."""
    return dataframe.dropna(how="all").reset_index(drop=True)


def _dataframe_profile(dataframe: pd.DataFrame) -> Dict[str, float]:
    """Calculate generic data quality measurements for one DataFrame."""
    rows, columns = dataframe.shape
    total_cells = rows * columns
    missing_values = int(dataframe.isna().sum().sum())
    duplicate_rows = int(dataframe.duplicated().sum()) if rows else 0
    completeness = (
        round(((total_cells - missing_values) / total_cells) * 100, 2)
        if total_cells
        else 100.0
    )
    uniqueness = (
        round(((rows - duplicate_rows) / rows) * 100, 2) if rows else 100.0
    )
    return {
        "rows": rows,
        "columns": columns,
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows,
        "completeness_pct": completeness,
        "uniqueness_pct": uniqueness,
    }


def _count_changed_cells(before: pd.DataFrame, after: pd.DataFrame) -> int:
    """Count changed values where row positions and column names overlap."""
    if len(before) != len(after):
        # Row additions/removals are reported separately; positional comparison
        # would incorrectly count shifted rows as edited cells.
        return 0
    common_columns = [column for column in before.columns if column in after.columns]
    common_rows = min(len(before), len(after))
    if not common_columns or not common_rows:
        return 0

    before_values = (
        before.loc[:, common_columns]
        .iloc[:common_rows]
        .reset_index(drop=True)
        .astype("string")
        .fillna("<NULL>")
    )
    after_values = (
        after.loc[:, common_columns]
        .iloc[:common_rows]
        .reset_index(drop=True)
        .astype("string")
        .fillna("<NULL>")
    )
    return int(before_values.ne(after_values).sum().sum())


class PipelineMetrics:
    """Collect step-level metrics and append them to a historical CSV file."""

    def __init__(self, metrics_path: Path, pipeline_name: str = "library_cleaning"):
        self.metrics_path = metrics_path
        self.pipeline_name = pipeline_name
        self.run_id = str(uuid.uuid4())
        self.run_timestamp_utc = utc_timestamp()
        self.records: List[Dict[str, Any]] = []
        self.step_numbers: Dict[str, int] = defaultdict(int)

    def _next_step_number(self, dataset: str) -> int:
        self.step_numbers[dataset] += 1
        return self.step_numbers[dataset]

    def record(
        self,
        dataset: str,
        step_name: str,
        before: pd.DataFrame,
        after: pd.DataFrame,
        duration_ms: float,
        status: str = "success",
        source_file: Optional[Path] = None,
        output_file: Optional[Path] = None,
        details: Optional[Dict[str, Any]] = None,
        quality_issue_count: Optional[int] = None,
        invalid_date_rows: Optional[int] = None,
        late_return_rows: Optional[int] = None,
        missing_key_rows: Optional[int] = None,
        blank_required_text_rows: Optional[int] = None,
        duplicate_key_rows: Optional[int] = None,
    ) -> None:
        """Add one step to the in-memory audit log."""
        before_profile = _dataframe_profile(before)
        after_profile = _dataframe_profile(after)
        added_names = sorted(set(after.columns).difference(before.columns))
        removed_names = sorted(set(before.columns).difference(after.columns))

        self.records.append(
            {
                "run_id": self.run_id,
                "run_timestamp_utc": self.run_timestamp_utc,
                "pipeline_name": self.pipeline_name,
                "dataset": dataset,
                "step_number": self._next_step_number(dataset),
                "step_name": step_name,
                "status": status,
                "rows_before": before_profile["rows"],
                "rows_after": after_profile["rows"],
                "rows_added": max(
                    after_profile["rows"] - before_profile["rows"], 0
                ),
                "rows_removed": max(
                    before_profile["rows"] - after_profile["rows"], 0
                ),
                "columns_before": before_profile["columns"],
                "columns_after": after_profile["columns"],
                "columns_added": len(added_names),
                "columns_removed": len(removed_names),
                "columns_added_names": "|".join(added_names),
                "columns_removed_names": "|".join(removed_names),
                "missing_values_before": before_profile["missing_values"],
                "missing_values_after": after_profile["missing_values"],
                "missing_values_removed": max(
                    before_profile["missing_values"]
                    - after_profile["missing_values"],
                    0,
                ),
                "duplicate_rows_before": before_profile["duplicate_rows"],
                "duplicate_rows_after": after_profile["duplicate_rows"],
                "duplicate_rows_removed": max(
                    before_profile["duplicate_rows"]
                    - after_profile["duplicate_rows"],
                    0,
                ),
                "completeness_before_pct": before_profile["completeness_pct"],
                "completeness_after_pct": after_profile["completeness_pct"],
                "uniqueness_before_pct": before_profile["uniqueness_pct"],
                "uniqueness_after_pct": after_profile["uniqueness_pct"],
                "changed_cells": _count_changed_cells(before, after),
                "quality_issue_count": quality_issue_count,
                "invalid_date_rows": invalid_date_rows,
                "late_return_rows": late_return_rows,
                "missing_key_rows": missing_key_rows,
                "blank_required_text_rows": blank_required_text_rows,
                "duplicate_key_rows": duplicate_key_rows,
                "processing_time_ms": round(duration_ms, 3),
                "source_file": str(source_file) if source_file else "",
                "output_file": str(output_file) if output_file else "",
                "details": json.dumps(details or {}, sort_keys=True),
            }
        )

    def apply(
        self,
        dataset: str,
        step_name: str,
        dataframe: pd.DataFrame,
        transformation: Callable[[pd.DataFrame], pd.DataFrame],
        details: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """Apply one transformation and automatically audit its effect."""
        before = dataframe.copy(deep=True)
        start_time = time.perf_counter()
        try:
            after = transformation(dataframe)
        except Exception as error:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.record(
                dataset,
                step_name,
                before,
                before,
                duration_ms,
                status="failed",
                details={"error": str(error), **(details or {})},
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        self.record(
            dataset,
            step_name,
            before,
            after,
            duration_ms,
            details=details,
        )
        return after

    def save(self) -> None:
        """Append this run to the metrics history without losing older runs."""
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        current_run = pd.DataFrame(self.records, columns=METRICS_COLUMNS)

        if self.metrics_path.exists():
            previous_runs = pd.read_csv(self.metrics_path)
            for column in METRICS_COLUMNS:
                if column not in previous_runs.columns:
                    previous_runs[column] = pd.NA
            combined = pd.concat(
                [previous_runs[METRICS_COLUMNS], current_run], ignore_index=True
            )
        else:
            combined = current_run

        combined = combined.drop_duplicates(
            subset=["run_id", "dataset", "step_number", "step_name"],
            keep="last",
        )
        combined.to_csv(self.metrics_path, index=False)


def _apply_or_run(
    dataframe: pd.DataFrame,
    transformation: Callable[[pd.DataFrame], pd.DataFrame],
    tracker: Optional[PipelineMetrics],
    dataset: str,
    step_name: str,
    details: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Keep the cleaning functions usable with or without metric tracking."""
    if tracker is None:
        return transformation(dataframe)
    return tracker.apply(dataset, step_name, dataframe, transformation, details)


def finalise_books(
    dataframe: pd.DataFrame,
    tracker: Optional[PipelineMetrics] = None,
) -> pd.DataFrame:
    """Standardise books data and add loan quality information."""
    books = _apply_or_run(
        dataframe,
        normalise_column_names,
        tracker,
        "books",
        "normalise_column_names",
    )
    books = _apply_or_run(
        books,
        remove_empty_rows,
        tracker,
        "books",
        "remove_fully_empty_rows",
    )
    books = _apply_or_run(
        books,
        lambda frame: require_columns(
            frame,
            ["id", "books", "book_checkout", "book_returned", "customer_id"],
            "Books",
        ),
        tracker,
        "books",
        "validate_required_columns",
    )
    books = _apply_or_run(
        books,
        lambda frame: strip_text_columns(frame, ["books"]),
        tracker,
        "books",
        "trim_book_titles",
    )
    books = _apply_or_run(
        books,
        lambda frame: convert_to_nullable_integer(frame, ["id", "customer_id"]),
        tracker,
        "books",
        "convert_identifier_types",
    )
    books = _apply_or_run(
        books,
        lambda frame: add_days_between(
            frame,
            start_date_column="book_checkout",
            end_date_column="book_returned",
            output_column="loan_days",
        ),
        tracker,
        "books",
        "parse_dates_and_calculate_loan_days",
        {"enrichment_column": "loan_days"},
    )
    books = _apply_or_run(
        books,
        add_book_quality_flags,
        tracker,
        "books",
        "add_late_and_invalid_date_flags",
        {"enrichment_columns": "returned_late|invalid_date_order"},
    )
    return _apply_or_run(
        books,
        remove_duplicate_rows,
        tracker,
        "books",
        "remove_duplicate_rows",
    )


def finalise_customers(
    dataframe: pd.DataFrame,
    tracker: Optional[PipelineMetrics] = None,
) -> pd.DataFrame:
    """Standardise customer identifiers and names."""
    customers = _apply_or_run(
        dataframe,
        normalise_column_names,
        tracker,
        "customers",
        "normalise_column_names",
    )
    customers = _apply_or_run(
        customers,
        remove_empty_rows,
        tracker,
        "customers",
        "remove_fully_empty_rows",
    )
    customers = _apply_or_run(
        customers,
        lambda frame: require_columns(
            frame, ["customer_id", "customer_name"], "Customers"
        ),
        tracker,
        "customers",
        "validate_required_columns",
    )
    customers = _apply_or_run(
        customers,
        lambda frame: convert_to_nullable_integer(frame, ["customer_id"]),
        tracker,
        "customers",
        "convert_identifier_type",
    )
    customers = _apply_or_run(
        customers,
        lambda frame: strip_text_columns(frame, ["customer_name"]),
        tracker,
        "customers",
        "trim_customer_names",
    )
    return _apply_or_run(
        customers,
        remove_duplicate_rows,
        tracker,
        "customers",
        "remove_duplicate_rows",
    )


def find_input_file(
    explicit_path: Optional[Path],
    dataset_name: str,
    filename_keywords: Sequence[str],
    fallback_clean_path: Path,
) -> Path:
    """Resolve a CLI path or discover a suitable source CSV."""
    if explicit_path:
        resolved = explicit_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Input file not found: {resolved}")
        return resolved

    search_directories = [BASE_DIRECTORY, BASE_DIRECTORY / "Raw_Data"]
    candidates: List[Path] = []
    for directory in search_directories:
        if directory.exists():
            candidates.extend(
                path
                for path in directory.glob("*.csv")
                if any(keyword in path.stem.lower() for keyword in filename_keywords)
                and "clean" not in path.stem.lower()
                and "metric" not in path.stem.lower()
            )

    if candidates:
        return sorted(candidates)[0]
    if fallback_clean_path.exists():
        return fallback_clean_path

    option_name = "books-input" if dataset_name == "books" else "customers-input"
    raise FileNotFoundError(
        f"No {dataset_name} input CSV was found. Put the raw file beside "
        f"this script, put it in Raw_Data, or supply --{option_name}."
    )


def record_loaded_data(
    tracker: PipelineMetrics,
    dataset: str,
    dataframe: pd.DataFrame,
    source_path: Path,
    duration_ms: float,
) -> None:
    """Record the initial source-file load."""
    tracker.record(
        dataset,
        "load_source_csv",
        pd.DataFrame(),
        dataframe,
        duration_ms,
        source_file=source_path,
        details={"file_name": source_path.name},
    )


def record_book_validation(
    tracker: PipelineMetrics,
    books: pd.DataFrame,
) -> None:
    """Record business-focused data quality indicators for books."""
    invalid_date_rows = int(books["invalid_date_order"].fillna(False).sum())
    missing_customer_ids = int(books["customer_id"].isna().sum())
    missing_loan_days = int(books["loan_days"].isna().sum())
    blank_titles = int(books["books"].fillna("").eq("").sum())
    late_return_rows = (
        int(books["returned_late"].fillna(False).sum())
        if "returned_late" in books.columns
        else 0
    )
    issues = invalid_date_rows + missing_customer_ids + missing_loan_days + blank_titles
    status = "passed" if issues == 0 else "warning"
    tracker.record(
        "books",
        "final_data_quality_validation",
        books,
        books,
        0.0,
        status=status,
        quality_issue_count=issues,
        invalid_date_rows=invalid_date_rows,
        late_return_rows=late_return_rows,
        missing_key_rows=missing_customer_ids,
        blank_required_text_rows=blank_titles,
        details={
            "blank_book_titles": blank_titles,
            "invalid_date_order_rows": invalid_date_rows,
            "late_return_rows": late_return_rows,
            "missing_customer_ids": missing_customer_ids,
            "missing_loan_days": missing_loan_days,
        },
    )


def record_customer_validation(
    tracker: PipelineMetrics,
    customers: pd.DataFrame,
) -> None:
    """Record business-focused data quality indicators for customers."""
    duplicate_ids = int(customers["customer_id"].duplicated(keep=False).sum())
    missing_ids = int(customers["customer_id"].isna().sum())
    blank_names = int(customers["customer_name"].fillna("").eq("").sum())
    issues = duplicate_ids + missing_ids + blank_names
    status = "passed" if issues == 0 else "warning"
    tracker.record(
        "customers",
        "final_data_quality_validation",
        customers,
        customers,
        0.0,
        status=status,
        quality_issue_count=issues,
        missing_key_rows=missing_ids,
        blank_required_text_rows=blank_names,
        duplicate_key_rows=duplicate_ids,
        details={
            "blank_customer_names": blank_names,
            "duplicate_customer_id_rows": duplicate_ids,
            "missing_customer_ids": missing_ids,
        },
    )


def save_clean_file(
    tracker: PipelineMetrics,
    dataset: str,
    dataframe: pd.DataFrame,
    output_path: Path,
    date_format: Optional[str] = None,
) -> None:
    """Save a clean dataset and record the output event."""
    start_time = time.perf_counter()
    dataframe.to_csv(output_path, index=False, date_format=date_format)
    duration_ms = (time.perf_counter() - start_time) * 1000
    tracker.record(
        dataset,
        "save_clean_csv",
        dataframe,
        dataframe,
        duration_ms,
        output_file=output_path,
        details={"file_name": output_path.name},
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Define optional command-line paths for different project layouts."""
    parser = argparse.ArgumentParser(
        description="Clean library data and generate Data Engineering metrics."
    )
    parser.add_argument(
        "--books-input",
        type=Path,
        help="Path to the raw books CSV. Auto-discovered when omitted.",
    )
    parser.add_argument(
        "--customers-input",
        type=Path,
        help="Path to the raw customers CSV. Auto-discovered when omitted.",
    )
    parser.add_argument(
        "--clean-dir",
        type=Path,
        default=DEFAULT_CLEAN_DATA_DIRECTORY,
        help="Directory for the clean outputs.",
    )
    parser.add_argument(
        "--metrics-path",
        type=Path,
        default=DEFAULT_METRICS_PATH,
        help="Historical metrics CSV path.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Load, clean, validate and save both datasets and the metrics history."""
    args = build_argument_parser().parse_args(argv)
    clean_directory = args.clean_dir.expanduser().resolve()
    metrics_path = args.metrics_path.expanduser().resolve()
    clean_directory.mkdir(parents=True, exist_ok=True)

    books_output_path = clean_directory / "library_books_clean.csv"
    customers_output_path = clean_directory / "library_customers_clean.csv"
    books_input_path = find_input_file(
        args.books_input, "books", ["book"], books_output_path
    )
    customers_input_path = find_input_file(
        args.customers_input,
        "customers",
        ["customer"],
        customers_output_path,
    )

    tracker = PipelineMetrics(metrics_path)
    print(f"Pipeline run ID: {tracker.run_id}")
    print(f"Books input: {books_input_path}")
    print(f"Customers input: {customers_input_path}")

    try:
        start_time = time.perf_counter()
        books_source = pd.read_csv(books_input_path)
        record_loaded_data(
            tracker,
            "books",
            books_source,
            books_input_path,
            (time.perf_counter() - start_time) * 1000,
        )

        start_time = time.perf_counter()
        customers_source = pd.read_csv(customers_input_path)
        record_loaded_data(
            tracker,
            "customers",
            customers_source,
            customers_input_path,
            (time.perf_counter() - start_time) * 1000,
        )

        books_final = finalise_books(books_source, tracker)
        customers_final = finalise_customers(customers_source, tracker)

        record_book_validation(tracker, books_final)
        record_customer_validation(tracker, customers_final)

        save_clean_file(
            tracker,
            "books",
            books_final,
            books_output_path,
            date_format="%Y-%m-%d",
        )
        save_clean_file(
            tracker,
            "customers",
            customers_final,
            customers_output_path,
        )
    finally:
        # A failed step is still valuable evidence and must reach the audit CSV.
        tracker.save()

    print("\nPipeline completed successfully.")
    print(f"Books output: {books_output_path}")
    print(f"Customers output: {customers_output_path}")
    print(f"Power BI metrics: {metrics_path}")
    print(f"Metric rows written for this run: {len(tracker.records)}")


if __name__ == "__main__":
    main()