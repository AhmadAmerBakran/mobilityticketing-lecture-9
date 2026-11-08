CREATE OR REPLACE FUNCTION lab09.book(
    p_request_id text,
    p_passenger_id text,
    p_trip_id text
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    v_booking_id bigint;
    v_existing lab09.bookings%ROWTYPE;
    v_trip_id text;
BEGIN
    INSERT INTO lab09.bookings (request_id, passenger_id, trip_id)
    VALUES (p_request_id, p_passenger_id, p_trip_id)
    ON CONFLICT (request_id) DO NOTHING
    RETURNING id INTO v_booking_id;

    IF NOT FOUND THEN
        SELECT *
        INTO v_existing
        FROM lab09.bookings
        WHERE request_id = p_request_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Request % must be retried', p_request_id
                USING ERRCODE = '40001';
        END IF;

        IF v_existing.passenger_id IS DISTINCT FROM p_passenger_id
           OR v_existing.trip_id IS DISTINCT FROM p_trip_id THEN
            RAISE EXCEPTION 'Request ID % was already used for another booking', p_request_id
                USING ERRCODE = '23505';
        END IF;

        RETURN v_existing.id;
    END IF;

    UPDATE lab09.trips
    SET reserved_seats = reserved_seats + 1
    WHERE id = p_trip_id
      AND status = 'Scheduled'
      AND reserved_seats < capacity
    RETURNING id INTO v_trip_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Trip % has no bookable seats', p_trip_id
            USING ERRCODE = 'P0001';
    END IF;

    RETURN v_booking_id;
END;
$$;
