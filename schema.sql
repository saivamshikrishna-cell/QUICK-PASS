CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    train TEXT NOT NULL,
    seat TEXT NOT NULL,
    from_station INTEGER NOT NULL,
    to_station INTEGER NOT NULL,
    journey_date TEXT NOT NULL,
    passenger_name TEXT NOT NULL,
    passenger_age INTEGER,
    payment_method TEXT NOT NULL DEFAULT 'demo',
    travel_class TEXT NOT NULL DEFAULT '3A',
    created_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    is_sample INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS reservations_segment_lookup
    ON reservations (train, journey_date, seat, status, from_station, to_station);

CREATE INDEX IF NOT EXISTS reservations_class_segment_lookup
    ON reservations (train, journey_date, travel_class, seat, status, from_station, to_station);

CREATE INDEX IF NOT EXISTS reservations_booking_list
    ON reservations (status, is_sample, journey_date, id);
