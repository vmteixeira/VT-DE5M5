Day 4 – Data Cleaning Metrics and Power BI Dashboard

Project objective



The purpose of this stage was to refactor the original day4\_notebook.py data-cleaning application so that it not only creates clean CSV files but also records Data Engineering metrics for every transformation.



The resulting metrics are written to a historical CSV file that can be loaded into Power BI to present data quality, processing and pipeline performance.



Pipeline architecture

flowchart LR

&#x20;   A\[Raw library CSV files] --> B\[Python cleaning pipeline]

&#x20;   B --> C\[Clean books CSV]

&#x20;   B --> D\[Clean customers CSV]

&#x20;   B --> E\[Engineering metrics CSV]

&#x20;   E --> F\[Power BI dashboard]



Source files

The pipeline processes the following raw datasets:

* 03\_Library Systembook(1).csv
* 03\_Library SystemCustomers(1).csv



The executable Python application is:

* day2\_notebook.py



Python cleaning stages



The Python application completes the following stages:



* Loads the books and customers source CSV files.
* Assigns a unique run\_id and UTC timestamp to the pipeline execution.
* Normalises column names into lowercase snake\_case format.
* Removes rows where every field is empty.
* Verifies that all required columns are available.
* Removes leading and trailing spaces from text fields.
* Parses the library dates using the UK DD/MM/YYYY format.
* Calculates the number of days between checkout and return dates.
* Converts values such as 2 weeks into a numeric 14-day allowance.
* Writes the cleaned books and customers datasets to CSV files.
* Appends the results of every stage to the Data Engineering metrics CSV.



The pipeline also identifies records where a return date occurs before the checkout date.



Running the pipeline



python .\\day2\_notebook.py



A successful execution creates:



metrics\\library\_books\_clean.csv

metrics\\library\_customers\_clean.csv

metrics\\data\_engineering\_metrics.csv



The metrics CSV contains one record for each pipeline stage.

The metrics file retains previous pipeline executions. Each new run is appended with a new run\_id, allowing Power BI to show historical trends.



Data-cleaning results



Measurement	Result

Raw book rows	114

Final book rows	21

Empty book rows removed	93

Raw customer rows	9

Final customer rows	8

Empty customer rows removed	1

Late returns identified	5

Invalid or reversed date sequences	6

Metric records generated	20



Power BI dashboard

Importing the metrics CSV

Open Power BI Desktop.

Select Get data.

Select Text/CSV.

Select day4\Data_Engineering_Metrics.csv.

