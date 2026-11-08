-- Run after sql/unsafe-read.sql with the same psql variables.
-- Intentionally omits the capacity predicate.
\if :can_book
UPDATE lab09.trips
SET reserved_seats = reserved_seats + 1
WHERE id = :'trip_id';

INSERT INTO lab09.bookings (request_id, passenger_id, trip_id)
VALUES (:'request_id', :'passenger_id', :'trip_id')
RETURNING id;
\else
\echo The prior read found no seat.
\endif
