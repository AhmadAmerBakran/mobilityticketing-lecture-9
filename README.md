# MobilityTicketing Lecture 9

Booking transactions on PostgreSQL 17. The schema, fixture, and supplied checks are from the Lecture 9 starter.

## Run

~~~sh
docker compose up -d --wait postgres
docker compose exec -T postgres bash /lab/run.sh reset
docker compose exec -T postgres bash /lab/run.sh check
docker compose exec -T postgres bash /lab/run.sh inspect
~~~

For two interactive sessions, open two terminals and run this in each:

~~~sh
docker compose exec postgres psql -X -U mobility -d mobility_l09 -v ON_ERROR_STOP=1 -v VERBOSITY=verbose
~~~

The final booking function is in sql/book.sql. Earlier approaches are kept in sql/variants. To try one, copy it to sql/book.sql and run the load command:

~~~sh
cp sql/variants/03-row-lock.sql sql/book.sql
docker compose exec -T postgres bash /lab/run.sh load
~~~

Restore the final version with:

~~~sh
cp sql/variants/07-idempotent.sql sql/book.sql
docker compose exec -T postgres bash /lab/run.sh reset
~~~

The experiments and observed results are in docs/evidence.md.

## Concurrent tests

The GitHub Actions workflow runs the original checks and a separate two-session test suite. To run it locally, use Python with psycopg:

~~~sh
python -m pip install "psycopg[binary]>=3.2,<4"
docker compose -f compose.yaml -f tests/compose.test.yaml up -d --wait postgres
docker compose -f compose.yaml -f tests/compose.test.yaml exec -T postgres bash /lab/run.sh reset
python tests/concurrency.py
~~~

The extra Compose file publishes PostgreSQL only on 127.0.0.1:5549. It is used for the Python tests, not for the normal lab setup.
