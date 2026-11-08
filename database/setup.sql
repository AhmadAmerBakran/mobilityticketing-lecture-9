\set ON_ERROR_STOP on

-- Reset this exercise only. Student SQL files remain on the host.
DROP SCHEMA IF EXISTS lab09 CASCADE;
CREATE SCHEMA lab09;

CREATE TABLE lab09.trips (
    id text PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('Scheduled', 'Cancelled')),
    capacity integer NOT NULL CHECK (capacity > 0),
    reserved_seats integer NOT NULL DEFAULT 0,
    CHECK (reserved_seats >= 0 AND reserved_seats <= capacity)
);

CREATE TABLE lab09.bookings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id text NOT NULL UNIQUE CHECK (length(request_id) > 0),
    passenger_id text NOT NULL CHECK (length(passenger_id) > 0),
    trip_id text NOT NULL REFERENCES lab09.trips(id),
    booked_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lab09.trips (id, status, capacity) VALUES
    ('T-LAST', 'Scheduled', 1),
    ('T-TWO', 'Scheduled', 2),
    ('T-CANCELLED', 'Cancelled', 1),
    ('T-OTHER', 'Scheduled', 2);

-- Install the current student function, initially a deliberate stub.
\ir ../sql/book.sql
