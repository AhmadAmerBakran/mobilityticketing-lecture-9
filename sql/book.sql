-- Your implementation goes here. Run `bash /lab/run.sh load` after editing.
-- The function runs in the caller's transaction; do not COMMIT inside it.
CREATE OR REPLACE FUNCTION lab09.book(
    p_request_id text,
    p_passenger_id text,
    p_trip_id text
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Implement lab09.book in sql/book.sql';
END;
$$;
