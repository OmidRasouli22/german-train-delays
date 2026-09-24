"""Build the train delay tables.

Three steps, in order. Reading the saved replies, then building the dbt
models and checking them, then writing the small files the dashboard uses.

Each step is the same command you would run by hand. Airflow only decides
when they run and what happens when one fails.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT = "/project"

default_args = {
    "owner": "omid",
    # The API and the disk both fail now and then. Try again before giving up.
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="trains",
    description="Turn the saved API replies into tables",
    default_args=default_args,
    start_date=datetime(2026, 9, 17),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["trains"],
) as dag:

    # Read any files that have not been read yet.
    parse = BashOperator(
        task_id="parse",
        bash_command="cd %s && python parse.py" % PROJECT,
    )

    # Build the models and run the tests. dbt build does both, and stops
    # if a test fails, so a broken table never reaches the dashboard.
    dbt = BashOperator(
        task_id="dbt_build",
        bash_command="cd %s/dbt && dbt build --profiles-dir ." % PROJECT,
    )

    # Write the small summary files the dashboard reads.
    export = BashOperator(
        task_id="export",
        bash_command="cd %s && python export_dashboard_data.py" % PROJECT,
    )

    parse >> dbt >> export
