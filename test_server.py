import tempfile
import unittest
from datetime import date
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
            "date": date.today().isoformat(),
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

    def test_requested_seat_is_rejected_if_its_segment_is_occupied(self):
        request = self.booking_request(0, 8)
        request["seat"] = "B1-01"
        with self.assertRaises(server.RequestError) as error:
            server.create_booking(request)
        self.assertEqual(error.exception.status, 409)

    def test_public_availability_does_not_expose_ticket_or_passenger_details(self):
        state = server.get_state()
        self.assertNotIn("bookings", state)
        self.assertTrue(state["reservations"])
        self.assertNotIn("id", state["reservations"][0])
        self.assertNotIn("name", state["reservations"][0])

    def test_cancellation_releases_the_route_segment(self):
        first = server.create_booking(self.booking_request(0, 2))
        server.cancel_booking(first["id"])
        second = server.create_booking(self.booking_request(0, 2))
        self.assertEqual(second["seat"], first["seat"])

    def test_unknown_payment_method_is_rejected(self):
        request = self.booking_request(0, 2)
        request["paymentMethod"] = "cash"
        with self.assertRaises(server.RequestError):
            server.create_booking(request)


if __name__ == "__main__":
    unittest.main()
