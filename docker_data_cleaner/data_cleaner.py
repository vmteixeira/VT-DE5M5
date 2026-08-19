#!/usr/bin/env python3
"""Clean library book and customer CSV files and print the results."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


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
    """Add the whole-day difference between two date columns."""
    enriched = dataframe.copy()
    start_dates = pd.to_datetime(enriched[start_date_column], errors="coerce")
    end_dates = pd.to_datetime(enriched[end_date_column], errors="coerce")
    enriched[start_date_column] = start_dates
    enriched[end_date_column] = end_dates
    enriched[output_column] = (end_dates - start_dates).dt.days.astype("Int64")
    return enriched


def finalise_books(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Standardise book records and calculate loan information."""
    books = normalise_column_names(dataframe)
    required_columns = {
        "id",
        "books",
        "book_checkout",
        "book_returned",
        "customer_id",
    }
    missing_columns = required_columns.difference(books.columns)
    if missing_columns:
        raise ValueError(f"Books file is missing columns: {sorted(missing_columns)}")

    books["books"] = books["books"].astype("string").str.strip()
    books["id"] = pd.to_numeric(books["id"], errors="coerce").astype("Int64")
    books["customer_id"] = pd.to_numeric(
        books["customer_id"], errors="coerce"
    ).astype("Int64")

    books = add_days_between(
        books,
        start_date_column="book_checkout",
        end_date_column="book_returned",
        output_column="loan_days",
    )

    if "days_allowed" in books.columns:
        books["days_allowed"] = pd.to_numeric(
            books["days_allowed"], errors="coerce"
        ).astype("Int64")
        books["returned_late"] = (
            books["loan_days"] > books["days_allowed"]
        ).astype("boolean")

    books["invalid_date_order"] = books["loan_days"].lt(0).astype("boolean")
    return books.drop_duplicates().reset_index(drop=True)


def finalise_customers(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Standardise customer records and remove duplicates."""
    customers = normalise_column_names(dataframe)
    required_columns = {"customer_id", "customer_name"}
    missing_columns = required_columns.difference(customers.columns)
    if missing_columns:
        raise ValueError(
            f"Customers file is missing columns: {sorted(missing_columns)}"
        )

    customers["customer_id"] = pd.to_numeric(
        customers["customer_id"], errors="coerce"
    ).astype("Int64")
    customers["customer_name"] = (
        customers["customer_name"].astype("string").str.strip()
    )
    return customers.drop_duplicates().reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean library CSV files and output all cleaned rows to the terminal."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("/data/input"),
        help="Directory containing the two input CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/data/output"),
        help="Directory where cleaned CSV files will be written.",
    )
    parser.add_argument(
        "--books-file",
        default="library_books_clean.csv",
        help="Books CSV filename within the input directory.",
    )
    parser.add_argument(
        "--customers-file",
        default="library_customers_clean.csv",
        help="Customers CSV filename within the input directory.",
    )
    return parser.parse_args()


def print_cleaned_data(title: str, dataframe: pd.DataFrame) -> None:
    """Print a complete DataFrame as CSV so container logs stay portable."""
    print(f"\n=== {title} ===")
    print(dataframe.to_csv(index=False, date_format="%Y-%m-%d").rstrip())


def main() -> None:
    args = parse_args()
    books_input = args.input_dir / args.books_file
    customers_input = args.input_dir / args.customers_file

    missing_files = [path for path in (books_input, customers_input) if not path.is_file()]
    if missing_files:
        missing = ", ".join(str(path) for path in missing_files)
        raise FileNotFoundError(f"Input file(s) not found: {missing}")

    books_final = finalise_books(pd.read_csv(books_input))
    customers_final = finalise_customers(pd.read_csv(customers_input))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    books_output = args.output_dir / args.books_file
    customers_output = args.output_dir / args.customers_file
    books_final.to_csv(books_output, index=False, date_format="%Y-%m-%d")
    customers_final.to_csv(customers_output, index=False)

    print_cleaned_data("CLEANED BOOKS", books_final)
    print_cleaned_data("CLEANED CUSTOMERS", customers_final)
    print(f"\nSaved cleaned files to {args.output_dir}")


if __name__ == "__main__":
    main()