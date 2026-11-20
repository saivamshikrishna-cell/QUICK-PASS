#!/usr/bin/env python3
"""QUICK PASS booking demo with SQLite locally and PostgreSQL when hosted."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "railway.sqlite3"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
HOST = os.environ.get("HOST", "0.0.0.0" if DATABASE_URL else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
TRAIN_NUMBER = "12750"
STATIONS = [
    "Sainagar Shirdi",
    "Kopargaon",
    "Manmad Junction",
    "Jalgaon Junction",
    "Bhusaval Junction",
    "Akola Junction",
    "Nanded",
    "Secunderabad Junction",
    "Hyderabad Deccan",
]
SEAT_CLASSES = {
    "general": {
        "label": "General (GEN)",
        "prefix": "G",
        "count": 12,
        "fare_percent": 55,
    },
    "sleeper": {
        "label": "Sleeper (SL)",
        "prefix": "S1",
        "count": 16,
        "fare_percent": 80,
    },
    "3A": {
        "label": "AC 3 Tier (3A)",
        "prefix": "B1",
        "count": 16,
        "fare_percent": 100,
    },
}
BERTH_TYPES = (
    "Lower berth",
    "Middle berth",
    "Upper berth",
    "Lower berth",
    "Middle berth",
    "Upper berth",
    "Side lower berth",
    "Side upper berth",
)
SEATS_BY_CLASS = {
    class_code: [
        f"{seat_class['prefix']}-{number:02d}"
        for number in range(1, seat_class["count"] + 1)
    ]
    for class_code, seat_class in SEAT_CLASSES.items()
}
SEATS = SEATS_BY_CLASS["3A"]
PAYMENT_METHODS = {
    "upi": "UPI (simulated)",
    "card": "Debit / credit card (simulated)",
    "netbanking": "Net banking (simulated)",
}
DATABASE_ERRORS = (sqlite3.Error,)
if DATABASE_URL:
    import psycopg
    from psycopg.rows import dict_row

    DATABASE_ERRORS += (psycopg.Error,)


class RequestError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def today_in_india():
    return datetime.now(INDIA_TIMEZONE).date()


def connect_database():
    if DATABASE_URL:
        return psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=10,
        )
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def execute(connection, query, parameters=()):
    if DATABASE_URL:
        query = re.sub(r"\?", "%s", query)
    return connection.execute(query, parameters)


@contextmanager
def database():
    connection = connect_database()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with database() as connection:
        execute(connection,
            """
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
            )
            """
        )
        execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS reservations_segment_lookup
            ON reservations (train, journey_date, seat, status, from_station, to_station)
            """,
        )
        execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS reservations_booking_list
            ON reservations (status, is_sample, journey_date, id)
            """,
        )
        if DATABASE_URL:
            execute(
                connection,
                "ALTER TABLE reservations ADD COLUMN IF NOT EXISTS "
                "payment_method TEXT NOT NULL DEFAULT 'demo'",
            )
            execute(
                connection,
                "ALTER TABLE reservations ADD COLUMN IF NOT EXISTS "
                "travel_class TEXT NOT NULL DEFAULT '3A'",
            )
            execute(
                connection,
                "ALTER TABLE reservations ADD COLUMN IF NOT EXISTS "
                "created_at TEXT NOT NULL DEFAULT ''",
            )
        else:
            columns = {
                row["name"]
                for row in execute(
                    connection, "PRAGMA table_info(reservations)"
                ).fetchall()
            }
            if "payment_method" not in columns:
                execute(
                    connection,
                    "ALTER TABLE reservations ADD COLUMN "
                    "payment_method TEXT NOT NULL DEFAULT 'demo'",
                )
            if "travel_class" not in columns:
                execute(
                    connection,
                    "ALTER TABLE reservations ADD COLUMN "
                    "travel_class TEXT NOT NULL DEFAULT '3A'",
                )
            if "created_at" not in columns:
                execute(
                    connection,
                    "ALTER TABLE reservations ADD COLUMN "
                    "created_at TEXT NOT NULL DEFAULT ''",
                )
        execute(
            connection,
            """
            CREATE INDEX IF NOT EXISTS reservations_class_segment_lookup
            ON reservations
                (train, journey_date, travel_class, seat, status, from_station, to_station)
            """,
        )
        sample_date = today_in_india()
        examples = [
            (f"sample-manmad-hyderabad-{sample_date.isoformat()}", "B1-01", 2, 8),
            (f"sample-jalgaon-secunderabad-{sample_date.isoformat()}", "B1-02", 3, 7),
            (f"sample-kopargaon-manmad-{sample_date.isoformat()}", "B1-03", 1, 2),
        ]
        for booking_id, seat, start, end in examples:
            execute(
                connection,
                """
                INSERT INTO reservations
                    (id, train, seat, from_station, to_station, journey_date,
                     passenger_name, status, is_sample)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed', 1)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    booking_id,
                    TRAIN_NUMBER,
                    seat,
                    start,
                    end,
                    sample_date.isoformat(),
                    "Sample passenger",
                ),
            )


def get_state():
    with database() as connection:
        reservations = execute(connection,
            """
            SELECT id, train, seat, from_station, to_station, journey_date,
                   travel_class, status
            FROM reservations
            WHERE status = 'confirmed'
            """
        ).fetchall()
        cancellations = execute(
            connection,
            """
            SELECT train, journey_date, travel_class, from_station, to_station,
                   COUNT(*) AS cancelled_count
            FROM reservations
            WHERE status = 'cancelled' AND is_sample = 0
            GROUP BY train, journey_date, travel_class, from_station, to_station
            """,
        ).fetchall()

    def as_reservation(row):
        return {
            "train": row["train"],
            "seat": row["seat"],
            "from": row["from_station"],
            "to": row["to_station"],
            "date": row["journey_date"],
            "travelClass": row["travel_class"],
            "status": row["status"],
        }

    def as_cancellation(row):
        return {
            "train": row["train"],
            "date": row["journey_date"],
            "travelClass": row["travel_class"],
            "from": row["from_station"],
            "to": row["to_station"],
            "count": row["cancelled_count"],
        }

    return {
        "reservations": [as_reservation(row) for row in reservations],
        "cancellations": [as_cancellation(row) for row in cancellations],
    }


def berth_type_for_seat(travel_class, seat):
    if travel_class == "general":
        return "Reserved seat"
    number = int(seat.rsplit("-", 1)[1])
    return BERTH_TYPES[(number - 1) % len(BERTH_TYPES)]


def validate_booking(payload):
    if not isinstance(payload, dict):
        raise RequestError("The booking details must be a JSON object.")

    train = payload.get("train")
    if train != TRAIN_NUMBER:
        raise RequestError("This demo train is not available.")

    try:
        start = int(payload.get("from"))
        end = int(payload.get("to"))
    except (TypeError, ValueError):
        raise RequestError("Choose valid starting and destination stations.")
    if start < 0 or end >= len(STATIONS) or start >= end:
        raise RequestError("The destination must come after the starting station.")

    journey_date = payload.get("date")
    try:
        parsed_date = date.fromisoformat(journey_date)
    except (TypeError, ValueError):
        raise RequestError("Enter a valid journey date.")
    if parsed_date.isoformat() != journey_date:
        raise RequestError("Journey date must use YYYY-MM-DD format.")
    if parsed_date < today_in_india():
        raise RequestError("Journey date cannot be in the past.")

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 70:
        raise RequestError("Enter a passenger name of 1 to 70 characters.")
    try:
        age = int(payload.get("age"))
    except (TypeError, ValueError):
        raise RequestError("Enter a valid passenger age.")
    if age < 1 or age > 120:
        raise RequestError("Passenger age must be between 1 and 120.")

    payment_method = payload.get("paymentMethod")
    if not isinstance(payment_method, str) or payment_method not in PAYMENT_METHODS:
        raise RequestError("Choose one of the available demo payment methods.")

    travel_class = payload.get("travelClass", "3A")
    if not isinstance(travel_class, str) or travel_class not in SEAT_CLASSES:
        raise RequestError("Choose General, Sleeper, or AC 3 Tier.")

    requested_seat = payload.get("seat")
    if requested_seat is not None and (
        not isinstance(requested_seat, str)
        or requested_seat not in SEATS_BY_CLASS[travel_class]
    ):
        raise RequestError("Choose a valid seat for the selected travel class.")

    return (
        train,
        start,
        end,
        journey_date,
        name.strip(),
        age,
        payment_method,
        travel_class,
        requested_seat,
    )


def create_booking(payload):
    (
        train,
        start,
        end,
        journey_date,
        name,
        age,
        payment_method,
        travel_class,
        requested_seat,
    ) = validate_booking(payload)
    with database() as connection:
        if DATABASE_URL:
            execute(
                connection,
                "SELECT pg_advisory_xact_lock(hashtext(?), hashtext(?))",
                (train, journey_date),
            )
        else:
            connection.execute("BEGIN IMMEDIATE")
        candidate_seats = (
            [requested_seat] if requested_seat else SEATS_BY_CLASS[travel_class]
        )
        for seat in candidate_seats:
            overlap = execute(connection,
                """
                SELECT 1 FROM reservations
                WHERE train = ? AND seat = ? AND journey_date = ?
                  AND travel_class = ?
                  AND status = 'confirmed'
                  AND from_station < ? AND ? < to_station
                LIMIT 1
                """,
                (train, seat, journey_date, travel_class, end, start),
            ).fetchone()
            if overlap is None:
                booking_id = "RL" + secrets.token_hex(16).upper()
                booked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                execute(connection,
                    """
                    INSERT INTO reservations
                        (id, train, seat, from_station, to_station, journey_date,
                         passenger_name, passenger_age, payment_method, travel_class,
                         created_at, status, is_sample)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 0)
                    """,
                    (
                        booking_id,
                        train,
                        seat,
                        start,
                        end,
                        journey_date,
                        name,
                        age,
                        payment_method,
                        travel_class,
                        booked_at,
                    ),
                )
                connection.commit()
                fare = max(
                    50,
                    (
                        865
                        * SEAT_CLASSES[travel_class]["fare_percent"]
                        * (end - start)
                        + 50 * (len(STATIONS) - 1)
                    )
                    // (100 * (len(STATIONS) - 1)),
                )
                return {
                    "id": booking_id,
                    "train": train,
                    "seat": seat,
                    "from": start,
                    "to": end,
                    "date": journey_date,
                    "travelClass": travel_class,
                    "classLabel": SEAT_CLASSES[travel_class]["label"],
                    "berthType": berth_type_for_seat(travel_class, seat),
                    "bookedAt": booked_at,
                    "name": name,
                    "age": age,
                    "paymentMethod": payment_method,
                    "paymentLabel": PAYMENT_METHODS[payment_method],
                    "fare": fare,
                    "status": "confirmed",
                }
        connection.rollback()
    if requested_seat:
        raise RequestError("That seat was just booked. Choose another available seat.", 409)
    raise RequestError("No seats are available for this route segment and date.", 409)


def cancel_booking(booking_id):
    with database() as connection:
        if not DATABASE_URL:
            connection.execute("BEGIN IMMEDIATE")
        result = execute(connection,
            """
            UPDATE reservations SET status = 'cancelled'
            WHERE id = ? AND is_sample = 0 AND status = 'confirmed'
            """,
            (booking_id,),
        )
        connection.commit()
        if result.rowcount == 0:
            raise RequestError("Booking not found or already cancelled.", 404)


class RailwayHandler(BaseHTTPRequestHandler):
    server_version = "QuickPassDemo/1.0"

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_database_error(self, error):
        self.log_error("Database request failed: %s", error)
        self.send_json(503, {"error": "The booking database is temporarily unavailable."})

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise RequestError("Invalid request length.")
        if length <= 0 or length > 16_384:
            raise RequestError("Request body must be between 1 byte and 16 KB.", 413)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RequestError("Request body must contain valid JSON.")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            try:
                with database() as connection:
                    execute(connection, "SELECT 1")
            except DATABASE_ERRORS as error:
                self.log_error("Health check failed: %s", error)
                self.send_json(503, {"status": "unavailable"})
                return
            self.send_json(200, {"status": "ok"})
            return
        if path == "/api/state":
            try:
                self.send_json(200, get_state())
            except DATABASE_ERRORS as error:
                self.send_database_error(error)
            return
        if path in ("/", "/index.html"):
            page = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)
            return
        self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        if urlsplit(self.path).path != "/api/bookings":
            self.send_json(404, {"error": "Not found."})
            return
        try:
            booking = create_booking(self.read_json())
        except RequestError as error:
            self.send_json(error.status, {"error": str(error)})
            return
        except DATABASE_ERRORS as error:
            self.send_database_error(error)
            return
        self.send_json(201, booking)

    def do_DELETE(self):
        prefix = "/api/bookings/"
        path = urlsplit(self.path).path
        if not path.startswith(prefix) or not path[len(prefix):]:
            self.send_json(404, {"error": "Not found."})
            return
        try:
            cancel_booking(path[len(prefix):])
        except RequestError as error:
            self.send_json(error.status, {"error": str(error)})
            return
        except DATABASE_ERRORS as error:
            self.send_database_error(error)
            return
        self.send_json(200, {"cancelled": True})

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args))


def main():
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), RailwayHandler)
    print(f"QUICK PASS demo running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Railway demo.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
