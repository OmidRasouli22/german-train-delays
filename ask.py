"""Run the questions in queries.sql against the collected data.

DuckDB reads the parquet file straight from disk, so there is no database
to load and no server to start.
"""

import sys

import duckdb

QUERY_FILE = "queries.sql"


def split_queries(text):
    """Split the file into single queries, keeping the comment above each."""
    queries = []
    current = []
    for line in text.split("\n"):
        current.append(line)
        if line.strip().endswith(";"):
            block = "\n".join(current).strip()
            if block:
                queries.append(block)
            current = []
    return queries


def title_of(query):
    """Use the first comment line as the heading."""
    for line in query.split("\n"):
        line = line.strip()
        if line.startswith("--") and len(line) > 3:
            return line.lstrip("-").strip()
    return "query"


def main():
    try:
        text = open(QUERY_FILE, encoding="utf-8").read()
    except FileNotFoundError:
        print("No %s found." % QUERY_FILE)
        return 1

    con = duckdb.connect()
    for query in split_queries(text):
        print()
        print(title_of(query))
        print("-" * 60)
        try:
            print(con.sql(query).df().to_string(index=False))
        except Exception as e:
            print("failed: %s" % str(e).split("\n")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
