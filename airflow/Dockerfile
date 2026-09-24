# Airflow with the packages this project needs.
#
# The plain Airflow image has no pandas, duckdb or dbt, so the tasks would
# fail as soon as they imported anything.

FROM apache/airflow:2.10.4-python3.12

COPY requirements.txt /tmp/requirements.txt

# Airflow pins its own dependencies, so install ours on top without letting
# pip pull a different version of something Airflow needs.
RUN pip install --no-cache-dir -r /tmp/requirements.txt
