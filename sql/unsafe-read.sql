-- Deliberately unsafe: the decision is kept in this session's variables.
-- Set trip_id, request_id and passenger_id first.
SELECT reserved_seats AS seen_reserved,
       status = 'Scheduled' AND reserved_seats < capacity AS can_book
FROM lab09.trips
WHERE id = :'trip_id'
\gset

\echo Observed reserved_seats=:seen_reserved; can_book=:can_book
