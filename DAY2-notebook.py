#!/usr/bin/env python
# coding: utf-8

# # Day 2 AM Goals:
# 
# 1. Get your notebook finalised so that it outputs two clean csv files.
# 2. Make sure that your cleaning uses one or more functions. MUST HAVE: a function to enrich the data. A function that works out the difference in days between the date columns. 
# 3. Turn your notebook into an executable .py file (manually).

# ### 1. Get your notebook finalised so that it outputs two clean csv files.

# In[10]:


# Import clean CSV files
import pandas as pd

BASE_DIRECTORY = Path.cwd()
CLEAN_DATA_DIRECTORY = BASE_DIRECTORY / "Clean_Data"
BOOKS_CLEAN_PATH = CLEAN_DATA_DIRECTORY / "library_books_clean.csv"
CUSTOMERS_CLEAN_PATH = CLEAN_DATA_DIRECTORY / "library_customers_clean.csv"

for clean_file in (BOOKS_CLEAN_PATH, CUSTOMERS_CLEAN_PATH):
    if not clean_file.exists():
        raise FileNotFoundError(
            f"Clean file not found: {clean_file}. "
            "Keep the notebook beside the Clean_Data folder."
        )

books_clean = pd.read_csv(BOOKS_CLEAN_PATH)
customers_clean = pd.read_csv(CUSTOMERS_CLEAN_PATH)

print(f"Books loaded: {books_clean.shape}")
print(f"Customers loaded: {customers_clean.shape}")
print("\nBooks preview:")
print(books_clean.head().to_string(index=False))
print("\nCustomers preview:")
print(customers_clean.head().to_string(index=False))



# In[3]:


# Load both clean files
import pandas as pd
books_path = next(
        file for file in csv_files
        if "books_clean" in file.name
)
customers_path = next(
        file for file in csv_files
        if "customers_clean" in file.name
)
books_df = pd.read_csv(books_path)
customers_df = pd.read_csv(customers_path)


# ### 2. Make sure that your cleaning uses one or more functions. MUST HAVE: a function to enrich the data. A function that works out the difference in days between the date columns. 

# In[11]:


# Calculate the days    
def normalise_column_names(dataframe: pd.DataFrame) -> pd.DataFrame:
    # Return a copy with lowercase snake_case column names.
    cleaned = dataframe.copy()
    cleaned.columns = (
        cleaned.columns.astype("string")
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return cleaned


# In[12]:


# Days between Dates
def add_days_between(
    dataframe: pd.DataFrame,
    start_date_column: str,
    end_date_column: str,
    output_column: str = "days_between",
) -> pd.DataFrame:
    # Enrich a DataFrame with the difference in days between two dates.
    enriched = dataframe.copy()
    start_dates = pd.to_datetime(enriched[start_date_column], errors="coerce")
    end_dates = pd.to_datetime(enriched[end_date_column], errors="coerce")
    enriched[start_date_column] = start_dates
    enriched[end_date_column] = end_dates
    enriched[output_column] = (end_dates - start_dates).dt.days.astype("Int64")
    return enriched


# In[13]:


# Standardise the clean books file and add the loan duration.
def finalise_books(dataframe: pd.DataFrame) -> pd.DataFrame:
    
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


# In[14]:


# Standardise the already-clean customers file.
def finalise_customers(dataframe: pd.DataFrame) -> pd.DataFrame:
    # Standardise the already-clean customers file.
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


# In[16]:


# Run functions and output final clean CSV files
books_final = finalise_books(books_clean)
customers_final = finalise_customers(customers_clean)

books_final.to_csv(
    BOOKS_CLEAN_PATH,
    index=False,
    date_format="%Y-%m-%d",
)
customers_final.to_csv(
    CUSTOMERS_CLEAN_PATH,
    index=False,
)

print("Final clean files saved:")
print(f" - {BOOKS_CLEAN_PATH}")
print(f" - {CUSTOMERS_CLEAN_PATH}")
print(f"Final book rows: {len(books_final)}")
print(f"Final customer rows: {len(customers_final)}")


# In[17]:


# Validate the enrichment and saved clean files
books_check = pd.read_csv(
    BOOKS_CLEAN_PATH,
    parse_dates=["book_checkout", "book_returned"],
)
customers_check = pd.read_csv(CUSTOMERS_CLEAN_PATH)

calculated_days = (
    books_check["book_returned"] - books_check["book_checkout"]
).dt.days

assert BOOKS_CLEAN_PATH.exists()
assert CUSTOMERS_CLEAN_PATH.exists()
assert "loan_days" in books_check.columns
assert books_check["loan_days"].equals(calculated_days)
assert customers_check["customer_id"].is_unique

print("Validation passed.")
print(f"{BOOKS_CLEAN_PATH.name}: {len(books_check)} rows")
print(f"{CUSTOMERS_CLEAN_PATH.name}: {len(customers_check)} rows")


# ## 3. Turn your notebook into an executable .py file (manually).

# In[18]:


# Save the notebook to open PowerShell
conversion_command = "jupyter nbconvert --to script eda.ipynb"
execution_command = "python eda.py"

print("Run these commands in PowerShell or Terminal:")
print(conversion_command)
print(execution_command)

