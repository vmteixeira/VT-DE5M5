from pathlib import Path

import pandas as pd

from day2_notebook import (
    add_days_between,
    finalise_books,
    finalise_customers,
)

def test_add_days_between():
    test_data = pd.DataFrame(
        {
        "book_checkout": ["2023-02-20"],
        "book_returned": ["2023-02-25"],
        }
    )
    
    result = add_days_between(
            test_data,
            start_data_column="book_checkout",
            end_data_column="book_returned",
            output_column="loan_days",
    )    
        
    assert result.loc[0, "loan_days"] == 5
    
    def test_finalise_books():
        test_data = pd.DataFrame(
            {
                "id": [1],
                "books": [" Test Book "],
                "book_checkout": ["2023-02-20"],
                "book_returned": ["2023-02-25"],
                "customer_id": [1],
                "days_allowed": [14],
            }
        )
    
        result = finalise_books(test_data)
    
        assert len(result) == 1
        assert result.loc[0, "books"] == "Test Book"
        assert result.loc[0, "loan_days"] == 5
        assert not bool(result.loc[0, "returned_late"])

    def test_finalise_customers():
        test_data = pd.DataFrame(
            {
                "customer_id": [1, 1],
                "customer_name": [
                    " Jane Doe ",
                    "Jane Doe",
                ],
            }
        )
    
        result = finalise_customers(test_data)
    
        assert len(result) == 1
        assert result.loc[0, "customer_id"] == 1
        assert result.loc[0, "customer_name"] == "Jane Doe"   