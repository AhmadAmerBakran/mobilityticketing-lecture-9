\set ON_ERROR_STOP on
\echo Checking the booking function in one session. Concurrent cases are in README.md.

BEGIN;
SET LOCAL lock_timeout = '5s';
TRUNCATE lab09.bookings RESTART IDENTITY;
UPDATE lab09.trips SET reserved_seats = 0;

CREATE FUNCTION pg_temp.expect_rejection(
    request_id text, passenger_id text, trip_id text
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    rejected boolean := false;
BEGIN
    BEGIN
        PERFORM lab09.book(request_id, passenger_id, trip_id);
    EXCEPTION WHEN OTHERS THEN
        rejected := true;
    END;
    IF NOT rejected THEN
        RAISE EXCEPTION 'Expected request % to be rejected', request_id;
    END IF;
END;
$$;

DO $$
DECLARE
    first_id bigint;
    repeated_id bigint;
    second_id bigint;
BEGIN
    first_id := lab09.book('check-first', 'passenger-A', 'T-LAST');
    IF first_id IS NULL OR NOT EXISTS (
        SELECT FROM lab09.bookings
        WHERE id = first_id AND request_id = 'check-first'
          AND passenger_id = 'passenger-A' AND trip_id = 'T-LAST'
    ) THEN
        RAISE EXCEPTION 'The function must return the stored booking ID';
    END IF;

    repeated_id := lab09.book('check-first', 'passenger-A', 'T-LAST');
    IF repeated_id IS DISTINCT FROM first_id THEN
        RAISE EXCEPTION 'A replay must return the original ID, even when full';
    END IF;
    UPDATE lab09.trips SET status = 'Cancelled' WHERE id = 'T-LAST';
    repeated_id := lab09.book('check-first', 'passenger-A', 'T-LAST');
    IF repeated_id IS DISTINCT FROM first_id THEN
        RAISE EXCEPTION 'A replay returns the existing booking after cancellation too';
    END IF;
    UPDATE lab09.trips SET status = 'Scheduled' WHERE id = 'T-LAST';

    PERFORM pg_temp.expect_rejection('check-full', 'passenger-B', 'T-LAST');
    PERFORM pg_temp.expect_rejection('check-first', 'passenger-B', 'T-LAST');
    PERFORM pg_temp.expect_rejection('check-first', 'passenger-A', 'T-OTHER');
    PERFORM pg_temp.expect_rejection('check-cancelled', 'passenger-A', 'T-CANCELLED');
    PERFORM pg_temp.expect_rejection('check-missing', 'passenger-A', 'T-MISSING');

    IF (SELECT count(*) FROM lab09.bookings) <> 1
       OR (SELECT sum(reserved_seats) FROM lab09.trips) <> 1 THEN
        RAISE EXCEPTION 'A replay or rejection changed bookings or reservations';
    END IF;

    first_id := lab09.book('check-two-a', 'passenger-A', 'T-TWO');
    second_id := lab09.book('check-two-b', 'passenger-B', 'T-TWO');
    IF first_id IS NULL OR second_id IS NULL OR first_id = second_id THEN
        RAISE EXCEPTION 'Two distinct successful requests need distinct booking IDs';
    END IF;
    PERFORM pg_temp.expect_rejection('check-two-c', 'passenger-C', 'T-TWO');

    -- A failure after a successful call must roll back both changes.
    BEGIN
        PERFORM lab09.book('check-rollback', 'passenger-A', 'T-OTHER');
        RAISE EXCEPTION USING ERRCODE = 'ZX001', MESSAGE = 'Simulated later failure';
    EXCEPTION WHEN SQLSTATE 'ZX001' THEN
        NULL;
    END;
    IF EXISTS (SELECT FROM lab09.bookings WHERE request_id = 'check-rollback')
       OR (SELECT reserved_seats FROM lab09.trips WHERE id = 'T-OTHER') <> 0 THEN
        RAISE EXCEPTION 'Rollback left a booking or a reserved seat behind';
    END IF;

    IF EXISTS (
        SELECT FROM lab09.trips AS t
        LEFT JOIN lab09.bookings AS b ON b.trip_id = t.id
        GROUP BY t.id
        HAVING t.reserved_seats <> count(b.id)
    ) OR (SELECT count(*) FROM lab09.bookings) <> 3 THEN
        RAISE EXCEPTION 'Final booking and reservation counts disagree';
    END IF;
END;
$$;

ROLLBACK;
\echo Single-session checks passed. Existing experiment data was restored.
