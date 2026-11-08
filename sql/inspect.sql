SELECT t.id, t.status, t.capacity, t.reserved_seats,
       count(b.id) AS booking_count,
       t.reserved_seats = count(b.id) AS counts_agree
FROM lab09.trips AS t
LEFT JOIN lab09.bookings AS b ON b.trip_id = t.id
GROUP BY t.id
ORDER BY t.id;

SELECT id, request_id, passenger_id, trip_id
FROM lab09.bookings
ORDER BY id;
