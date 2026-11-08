-- Deliberately unsafe: the WHERE clause does not recheck availability.
-- Both sessions can write the same stale value while the CHECK still passes.
\if :can_book
UPDATE lab09.trips
SET reserved_seats = :seen_reserved + 1
WHERE id = :'trip_id';

INSERT INTO lab09.bookings (request_id, passenger_id, trip_id)
VALUES (:'request_id', :'passenger_id', :'trip_id')
RETURNING id;
\else
\echo The read found no available seat. No booking was written.
\endif
