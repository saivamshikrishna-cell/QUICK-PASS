import tempfile
import unittest
from pathlib import Path

import server


class SeatAllocationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database = server.DATABASE
        server.DATABASE = Path(self.temp_dir.name) / "test.sqlite3"
        server.initialize_database()

    def tearDown(self):
        server.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def booking_request(self, start, end):
        return {
            "train": server.TRAIN_NUMBER,
            "from": start,
            "to": end,
            "date": server.today_in_india().isoformat(),
            "name": "Test passenger",
            "age": 30,
            "paymentMethod": "upi",
        }

    def test_non_overlapping_journey_can_share_a_seat(self):
        ticket = server.create_booking(self.booking_request(0, 2))
        self.assertEqual(ticket["seat"], "B1-01")
        self.assertEqual(ticket["paymentMethod"], "upi")
        self.assertEqual(ticket["fare"], 216)

    def test_overlapping_journey_cannot_use_an_occupied_seat(self):
        ticket = server.create_booking(self.booking_request(0, 3))
        self.assertNotEqual(ticket["seat"], "B1-01")

    def test_requested_available_seat_is_allocated(self):
        request = self.booking_request(0, 2)
        request["seat"] = "B1-08"
        ticket = server.create_booking(request)
        self.assertEqual(ticket["seat"], "B1-08")

    def test_booking_includes_berth_type_for_each_sleeper_position(self):
        expected_types = {
            "B1-01": "Lower berth",
            "B1-02": "Middle berth",
            "B1-03": "Upper berth",
            "B1-07": "Side lower berth",
            "B1-08": "Side upper berth",
            "B1-16": "Side upper berth",
        }
        for seat, berth_type in expected_types.items():
            request = self.booking_request(0, 1)
            request["seat"] = seat
            ticket = server.create_booking(request)
            self.assertEqual(ticket["berthType"], berth_type)

    def test_general_booking_is_labeled_as_a_reserved_seat(self):
        request = self.booking_request(0, 1)
        request["travelClass"] = "general"
        request["seat"] = "G-01"
        ticket = server.create_booking(request)
        self.assertEqual(ticket["berthType"], "Reserved seat")

    def test_requested_seat_is_rejected_if_its_segment_is_occupied(self):
        request = self.booking_request(0, 8)
        request["seat"] = "B1-01"
        with self.assertRaises(server.RequestError) as error:
            server.create_booking(request)
        self.assertEqual(error.exception.status, 409)

    def test_seat_classes_have_independent_segment_availability(self):
        ac_ticket = server.create_booking(self.booking_request(0, 2))
        sleeper_request = self.booking_request(0, 2)
        sleeper_request.update({"travelClass": "sleeper", "seat": "S1-01"})
        sleeper_ticket = server.create_booking(sleeper_request)
        self.assertEqual(ac_ticket["seat"], "B1-01")
        self.assertEqual(sleeper_ticket["seat"], "S1-01")
        self.assertEqual(sleeper_ticket["travelClass"], "sleeper")

    def test_seat_must_belong_to_selected_class(self):
        request = self.booking_request(0, 2)
        request.update({"travelClass": "general", "seat": "B1-01"})
        with self.assertRaises(server.RequestError):
            server.create_booking(request)

    def test_existing_database_is_migrated_to_class_and_booking_time(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        server.DATABASE = legacy_path
        connection = server.sqlite3.connect(legacy_path)
        try:
            connection.execute(
                """
                CREATE TABLE reservations (
                    id TEXT PRIMARY KEY, train TEXT NOT NULL, seat TEXT NOT NULL,
                    from_station INTEGER NOT NULL, to_station INTEGER NOT NULL,
                    journey_date TEXT NOT NULL, passenger_name TEXT NOT NULL,
                    passenger_age INTEGER, payment_method TEXT NOT NULL DEFAULT 'demo',
                    status TEXT NOT NULL, is_sample INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                INSERT INTO reservations
                    (id, train, seat, from_station, to_station, journey_date,
                     passenger_name, status)
                VALUES ('legacy-ticket', ?, 'B1-12', 0, 1, ?, 'Legacy passenger', 'confirmed')
                """,
                (server.TRAIN_NUMBER, server.today_in_india().isoformat()),
            )
            connection.commit()
        finally:
            connection.close()
        server.initialize_database()
        with server.database() as connection:
            row = server.execute(
                connection,
                "SELECT travel_class, created_at FROM reservations WHERE id = ?",
                ("legacy-ticket",),
            ).fetchone()
        self.assertEqual(row["travel_class"], "3A")
        self.assertEqual(row["created_at"], "")

    def test_booking_includes_a_server_booking_timestamp(self):
        ticket = server.create_booking(self.booking_request(0, 2))
        self.assertTrue(ticket["bookedAt"].endswith("+00:00"))

    def test_public_availability_does_not_expose_ticket_or_passenger_details(self):
        state = server.get_state()
        self.assertNotIn("bookings", state)
        self.assertTrue(state["reservations"])
        self.assertNotIn("id", state["reservations"][0])
        self.assertNotIn("name", state["reservations"][0])
        self.assertEqual(state["cancellations"], [])

    def test_cancellation_releases_the_route_segment(self):
        first = server.create_booking(self.booking_request(0, 2))
        server.cancel_booking(first["id"])
        second = server.create_booking(self.booking_request(0, 2))
        self.assertEqual(second["seat"], first["seat"])

    def test_cancellation_count_is_public_and_released_seat_can_be_rebooked(self):
        request = self.booking_request(0, 2)
        first = server.create_booking(request)
        server.cancel_booking(first["id"])

        state = server.get_state()
        self.assertEqual(
            state["cancellations"],
            [{
                "train": server.TRAIN_NUMBER,
                "date": request["date"],
                "travelClass": "3A",
                "from": 0,
                "to": 2,
                "count": 1,
            }],
        )
        self.assertNotIn("id", state["cancellations"][0])
        self.assertNotIn("name", state["cancellations"][0])

        second_request = {**request, "name": "Next passenger"}
        second = server.create_booking(second_request)
        self.assertEqual(second["seat"], first["seat"])
        refreshed_state = server.get_state()
        self.assertEqual(refreshed_state["cancellations"][0]["count"], 1)
        self.assertTrue(any(
            reservation["seat"] == first["seat"]
            and reservation["from"] == request["from"]
            and reservation["to"] == request["to"]
            for reservation in refreshed_state["reservations"]
        ))

    def test_cancellation_releases_the_seat_in_its_selected_class(self):
        request = self.booking_request(0, 2)
        request["travelClass"] = "general"
        first = server.create_booking(request)
        server.cancel_booking(first["id"])
        second = server.create_booking(request)
        self.assertEqual(second["seat"], first["seat"])
        self.assertEqual(second["travelClass"], "general")

    def test_unknown_payment_method_is_rejected(self):
        request = self.booking_request(0, 2)
        request["paymentMethod"] = "cash"
        with self.assertRaises(server.RequestError):
            server.create_booking(request)


if __name__ == "__main__":
    unittest.main()
