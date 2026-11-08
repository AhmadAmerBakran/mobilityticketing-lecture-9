CREATE OR REPLACE FUNCTION lab09.book(
    p_request_id text, p_passenger_id text, p_trip_id text
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_trip lab09.trips%ROWTYPE;
    v_booking_id bigint;
BEGIN
    LOCK TABLE lab09.trips IN EXCLUSIVE MODE;

    SELECT *
    INTO v_trip
    FROM lab09.trips
    WHERE id = p_trip_id;

    IF NOT FOUND OR v_trip.status <> 'Scheduled'
       OR v_trip.reserved_seats >= v_trip.capacity THEN
        RAISE EXCEPTION 'Trip % has no bookable seats', p_trip_id;
    END IF;

    UPDATE lab09.trips
    SET reserved_seats = reserved_seats + 1
    WHERE id = p_trip_id;

    INSERT INTO lab09.bookings (request_id, passenger_id, trip_id)
    VALUES (p_request_id, p_passenger_id, p_trip_id)
    RETURNING id INTO v_booking_id;

    RETURN v_booking_id;
END;
$$;
