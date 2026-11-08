CREATE OR REPLACE FUNCTION lab09.book(
    p_request_id text, p_passenger_id text, p_trip_id text
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_seen integer;
    v_trip text;
    v_booking_id bigint;
BEGIN
    SELECT reserved_seats INTO v_seen
    FROM lab09.trips
    WHERE id = p_trip_id
      AND status = 'Scheduled'
      AND reserved_seats < capacity;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Trip % has no bookable seats', p_trip_id;
    END IF;

    UPDATE lab09.trips
    SET reserved_seats = reserved_seats + 1
    WHERE id = p_trip_id
      AND status = 'Scheduled'
      AND reserved_seats = v_seen
      AND reserved_seats < capacity
    RETURNING id INTO v_trip;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Seat count changed; retry the transaction'
            USING ERRCODE = '40001';
    END IF;

    INSERT INTO lab09.bookings (request_id, passenger_id, trip_id)
    VALUES (p_request_id, p_passenger_id, p_trip_id)
    RETURNING id INTO v_booking_id;

    RETURN v_booking_id;
END;
$$;
