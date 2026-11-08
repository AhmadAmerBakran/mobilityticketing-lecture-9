"""Two-connection booking experiments against the PostgreSQL 17 fixture."""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
DSN = os.getenv("BOOKING_TEST_DSN", "postgresql://mobility:mobility@127.0.0.1:5549/mobility_l09")
POOL = ThreadPoolExecutor(max_workers=4)


def connect(name="test"):
    return psycopg.connect(DSN, autocommit=True, application_name=name)


def begin(conn, level="READ COMMITTED"):
    conn.execute(f"BEGIN ISOLATION LEVEL {level}")


def end(conn, commit=True):
    conn.execute("COMMIT" if commit else "ROLLBACK")


def reset():
    with connect() as conn:
        conn.execute("TRUNCATE lab09.bookings RESTART IDENTITY")
        conn.execute("""
            UPDATE lab09.trips
            SET reserved_seats = 0,
                status = CASE WHEN id = 'T-CANCELLED'
                              THEN 'Cancelled' ELSE 'Scheduled' END
        """)


def load(name):
    sql = (ROOT / "sql" / "variants" / name).read_text()
    with connect() as conn:
        conn.execute(sql)


def book(conn, request, passenger, trip):
    return conn.execute(
        "SELECT lab09.book(%s, %s, %s)",
        (request, passenger, trip),
    ).fetchone()[0]


def insert(conn, request, passenger, trip):
    conn.execute(
        "INSERT INTO lab09.bookings (request_id, passenger_id, trip_id) VALUES (%s, %s, %s)",
        (request, passenger, trip),
    )


def seats(trip):
    with connect() as conn:
        return tuple(conn.execute("""
            SELECT t.reserved_seats, count(b.id)::integer
            FROM lab09.trips AS t
            LEFT JOIN lab09.bookings AS b ON b.trip_id = t.id
            WHERE t.id = %s GROUP BY t.id
        """, (trip,)).fetchone())


def wait_for(name):
    with connect("observer") as conn:
        for _ in range(300):
            row = conn.execute("""
                SELECT wait_event_type, wait_event
                FROM pg_stat_activity
                WHERE application_name = %s AND state = 'active'
            """, (name,)).fetchone()
            if row and row[0] == "Lock":
                return f"Lock/{row[1]}"
            time.sleep(0.025)
    raise AssertionError(f"{name} did not reach a PostgreSQL lock wait")


def result(label, level, order, wait, state, trip="T-LAST"):
    reserved, bookings = seats(trip)
    print("RESULT " + json.dumps({
        "experiment": label,
        "isolation": level,
        "order": order,
        "wait": wait,
        "sqlstate": state or "none",
        "trip": trip,
        "reserved_seats": reserved,
        "bookings": bookings,
    }), flush=True)


def failed_call(conn, *args):
    try:
        book(conn, *args)
    except psycopg.Error as err:
        return err.sqlstate
    raise AssertionError(f"Expected rejection for {args}")


def unsafe(level, increment=False):
    reset()
    a, b = connect("unsafe-A"), connect("unsafe-B")
    try:
        begin(a, level)
        begin(b, level)
        seen_a = a.execute("SELECT reserved_seats FROM lab09.trips WHERE id = 'T-LAST'").fetchone()[0]
        seen_b = b.execute("SELECT reserved_seats FROM lab09.trips WHERE id = 'T-LAST'").fetchone()[0]
        assert seen_a == seen_b == 0

        if increment:
            a.execute("UPDATE lab09.trips SET reserved_seats = reserved_seats + 1 WHERE id = 'T-LAST'")
        else:
            a.execute("UPDATE lab09.trips SET reserved_seats = %s WHERE id = 'T-LAST'", (seen_a + 1,))
        insert(a, "unsafe-A", "passenger-A", "T-LAST")

        if increment:
            insert(b, "unsafe-B", "passenger-B", "T-LAST")
            future = POOL.submit(
                b.execute,
                "UPDATE lab09.trips SET reserved_seats = reserved_seats + 1 WHERE id = 'T-LAST'",
            )
            wait = wait_for("unsafe-B")
            end(a)
            try:
                future.result(timeout=12)
                raise AssertionError("The increment should violate the counter CHECK")
            except psycopg.Error as err:
                assert err.sqlstate == "23514", err.sqlstate
                state = err.sqlstate
            end(b, False)
            assert seats("T-LAST") == (1, 1)
        else:
            end(a)
            try:
                b.execute("UPDATE lab09.trips SET reserved_seats = %s WHERE id = 'T-LAST'", (seen_b + 1,))
            except psycopg.Error as err:
                state = err.sqlstate
                assert state == "40001", state
                end(b, False)
            else:
                insert(b, "unsafe-B", "passenger-B", "T-LAST")
                end(b)
                state = None
            wait = "none (B wrote after A committed)"
            expected = (1, 2) if level == "READ COMMITTED" else (1, 1)
            assert seats("T-LAST") == expected
        result(
            "increment CHECK" if increment else f"unsafe {level}",
            level,
            "A read, B read, A write/commit, B write",
            wait, state,
        )
        if state == "40001":
            with connect() as retry:
                begin(retry, level)
                remaining = retry.execute(
                    "SELECT capacity - reserved_seats FROM lab09.trips WHERE id = 'T-LAST'"
                ).fetchone()[0]
                assert remaining == 0
                end(retry)
    finally:
        a.close()
        b.close()


def competing(name, commit_a, same_trip=True):
    load(name)
    reset()
    trip_b = "T-LAST" if same_trip else "T-OTHER"
    a, b = connect("booking-A"), connect("booking-B")
    try:
        begin(a)
        begin(b)
        book(a, "request-A", "passenger-A", "T-LAST")
        future = POOL.submit(book, b, "request-B", "passenger-B", trip_b)
        wait = wait_for("booking-B") if (same_trip or name == "04-table-lock.sql") else "none"
        if wait == "none":
            assert future.result(timeout=5)
        end(a, commit_a)
        if same_trip and commit_a:
            try:
                future.result(timeout=12)
                raise AssertionError("Overbooking was accepted")
            except psycopg.Error as err:
                state = err.sqlstate
                end(b, False)
        else:
            assert future.result(timeout=12)
            end(b)
            state = None
        assert seats(trip_b) == (1, 1)
        if not same_trip:
            assert seats("T-LAST") == ((1, 1) if commit_a else (0, 0))
        result(
            f"{name} A {'commit' if commit_a else 'rollback'}"
            + (" same trip" if same_trip else " other trip"),
            "READ COMMITTED", "A book/open, B book, A end, B end", wait, state, trip_b,
        )
    finally:
        a.close()
        b.close()


def advisory_bypass():
    load("05-advisory-lock.sql")
    reset()
    a, b = connect("advisory-A"), connect("advisory-B")
    try:
        begin(a)
        book(a, "advisory-A", "passenger-A", "T-LAST")
        begin(b)
        stale = b.execute("SELECT reserved_seats FROM lab09.trips WHERE id = 'T-LAST'").fetchone()[0]
        assert stale == 0

        def write_without_advisory():
            b.execute("UPDATE lab09.trips SET reserved_seats = %s WHERE id = 'T-LAST'", (stale + 1,))
            insert(b, "advisory-B", "passenger-B", "T-LAST")

        future = POOL.submit(write_without_advisory)
        wait = wait_for("advisory-B")
        end(a)
        future.result(timeout=12)
        end(b)
        assert seats("T-LAST") == (1, 2)
        result("advisory bypass", "READ COMMITTED",
               "A advisory book/open, B stale read/update, A commit", wait, None)
    finally:
        a.close()
        b.close()


def deadlock():
    reset()
    a, b = connect("deadlock-A"), connect("deadlock-B")
    try:
        begin(a)
        begin(b)
        a.execute("SELECT id FROM lab09.trips WHERE id = 'T-LAST' FOR UPDATE")
        b.execute("SELECT id FROM lab09.trips WHERE id = 'T-OTHER' FOR UPDATE")

        def second_lock(conn, trip):
            try:
                conn.execute("SELECT id FROM lab09.trips WHERE id = %s FOR UPDATE", (trip,))
                return "ok"
            except psycopg.Error as err:
                conn.execute("ROLLBACK")
                return err.sqlstate

        first = POOL.submit(second_lock, a, "T-OTHER")
        wait_for("deadlock-A")
        second = POOL.submit(second_lock, b, "T-LAST")
        left = first.result(timeout=15)
        right = second.result(timeout=15)
        assert sorted([left, right]) == ["40P01", "ok"], (left, right)
        if left == "ok":
            end(a)
        if right == "ok":
            end(b)
        assert seats("T-LAST") == (0, 0)
        result("row-lock deadlock", "READ COMMITTED",
               "A locks LAST, B locks OTHER, A requests OTHER, B requests LAST",
               "both", "40P01")
    finally:
        a.close()
        b.close()


def optimistic(trip, rollback_a=False):
    reset()
    a, b = connect("optimistic-A"), connect("optimistic-B")
    try:
        begin(a)
        begin(b)
        seen_a = a.execute("SELECT reserved_seats FROM lab09.trips WHERE id = %s", (trip,)).fetchone()[0]
        seen_b = b.execute("SELECT reserved_seats FROM lab09.trips WHERE id = %s", (trip,)).fetchone()[0]
        assert seen_a == seen_b == 0
        changed = a.execute("""
            UPDATE lab09.trips SET reserved_seats = reserved_seats + 1
            WHERE id = %s AND status = 'Scheduled'
              AND reserved_seats = %s AND reserved_seats < capacity
            RETURNING id
        """, (trip, seen_a)).fetchone()
        assert changed
        insert(a, "optimistic-A", "passenger-A", trip)

        def b_update():
            return b.execute("""
                UPDATE lab09.trips SET reserved_seats = reserved_seats + 1
                WHERE id = %s AND status = 'Scheduled'
                  AND reserved_seats = %s AND reserved_seats < capacity
                RETURNING id
            """, (trip, seen_b)).fetchone()

        future = POOL.submit(b_update)
        wait = wait_for("optimistic-B")
        end(a, not rollback_a)
        updated = future.result(timeout=12)
        if rollback_a:
            assert updated
            insert(b, "optimistic-B", "passenger-B", trip)
            end(b)
            assert seats(trip) == (1, 1)
        else:
            assert updated is None
            end(b, False)
            begin(b)
            current, capacity = b.execute(
                "SELECT reserved_seats, capacity FROM lab09.trips WHERE id = %s", (trip,)
            ).fetchone()
            if current < capacity:
                changed = b.execute("""
                    UPDATE lab09.trips SET reserved_seats = reserved_seats + 1
                    WHERE id = %s AND reserved_seats = %s AND reserved_seats < capacity
                    RETURNING id
                """, (trip, current)).fetchone()
                assert changed
                insert(b, "optimistic-B", "passenger-B", trip)
            end(b)
            expected = (2, 2) if trip == "T-TWO" else (1, 1)
            assert seats(trip) == expected
        result(f"optimistic {trip} A {'rollback' if rollback_a else 'commit'}",
               "READ COMMITTED", "A/B read, A write, B write waits, A ends, B retries",
               wait, "zero rows" if not rollback_a else None, trip)
    finally:
        a.close()
        b.close()


def repeat_request(commit_a=True, passenger_b="passenger-A", trip_b="T-TWO"):
    load("07-idempotent.sql")
    reset()
    a, b = connect("replay-A"), connect("replay-B")
    try:
        begin(a)
        begin(b)
        first = book(a, "repeat-A", "passenger-A", "T-TWO")
        future = POOL.submit(book, b, "repeat-A", passenger_b, trip_b)
        wait = wait_for("replay-B")
        end(a, commit_a)
        if commit_a and (passenger_b, trip_b) != ("passenger-A", "T-TWO"):
            try:
                future.result(timeout=12)
                raise AssertionError("A mismatched request was accepted")
            except psycopg.Error as err:
                assert err.sqlstate == "23505"
                state = err.sqlstate
                end(b, False)
        else:
            replay = future.result(timeout=12)
            if commit_a:
                assert replay == first
            end(b)
            state = None
        assert seats("T-TWO") == ((1, 1) if commit_a else (0, 0)) or (
            not commit_a and trip_b == "T-TWO" and seats("T-TWO") == (1, 1)
        )
        result(
            f"request replay A {'commit' if commit_a else 'rollback'}"
            + (" changed payload" if (passenger_b, trip_b) != ("passenger-A", "T-TWO") else ""),
            "READ COMMITTED", "A inserts/open, B same request, A ends, B returns",
            wait, state, trip_b,
        )
    finally:
        a.close()
        b.close()


def final_checks():
    load("07-idempotent.sql")
    reset()
    with connect() as c:
        first = book(c, "once", "passenger-A", "T-LAST")
        assert book(c, "once", "passenger-A", "T-LAST") == first
        c.execute("UPDATE lab09.trips SET status = 'Cancelled' WHERE id = 'T-LAST'")
        assert book(c, "once", "passenger-A", "T-LAST") == first
        for args in [
            ("once", "passenger-B", "T-LAST"),
            ("once", "passenger-A", "T-OTHER"),
            ("new-full", "passenger-B", "T-LAST"),
            ("new-cancel", "passenger-A", "T-CANCELLED"),
            ("new-missing", "passenger-A", "T-MISSING"),
        ]:
            assert failed_call(c, *args)
        assert seats("T-LAST") == (1, 1)
        result("replay and rejection checks", "READ COMMITTED",
               "book, replay, cancel, replay, reject changed/full/cancelled/missing",
               "none", "23505/P0001/23503")
    reset()
    with connect() as c:
        begin(c)
        assert book(c, "rollback-ID", "passenger-A", "T-LAST")
        end(c, False)
        assert seats("T-LAST") == (0, 0)
        result("rollback after returned ID", "READ COMMITTED",
               "book returns ID, caller rolls back", "none", None)


def main():
    load("07-idempotent.sql")
    unsafe("READ COMMITTED")
    unsafe("READ COMMITTED", increment=True)
    for variant in ["02-conditional.sql", "03-row-lock.sql", "04-table-lock.sql", "05-advisory-lock.sql", "06-optimistic.sql"]:
        for commit_a in (True, False):
            competing(variant, commit_a)
        competing(variant, True, same_trip=False)
    advisory_bypass()
    deadlock()
    for trip in ("T-TWO", "T-LAST"):
        optimistic(trip)
    optimistic("T-LAST", rollback_a=True)
    for level in ("REPEATABLE READ", "SERIALIZABLE"):
        unsafe(level)
    final_checks()
    repeat_request()
    repeat_request(commit_a=False)
    repeat_request(passenger_b="passenger-B")
    repeat_request(commit_a=False, passenger_b="passenger-B")
    print("All concurrency experiments passed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        POOL.shutdown(wait=True)
