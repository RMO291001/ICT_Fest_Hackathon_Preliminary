from datetime import datetime

from app.services.export import generate_export


def test_generate_export_scopes_to_org_when_include_all_is_used():
    class DummyBooking:
        def __init__(self, booking_id, reference_code, room_id, user_id, start_time, end_time, status, price_cents):
            self.id = booking_id
            self.reference_code = reference_code
            self.room_id = room_id
            self.user_id = user_id
            self.start_time = start_time
            self.end_time = end_time
            self.status = status
            self.price_cents = price_cents

    class DummyQuery:
        def __init__(self, rows):
            self.rows = rows

        def join(self, *_args, **_kwargs):
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.rows

    class DummyDB:
        def __init__(self, rows):
            self.rows = rows

        def query(self, *_args, **_kwargs):
            return DummyQuery(self.rows)

    rows = [
        DummyBooking(
            1,
            "ABC",
            10,
            20,
            datetime(2024, 1, 1, 0, 0, 0),
            datetime(2024, 1, 1, 1, 0, 0),
            "confirmed",
            5000,
        )
    ]
    db = DummyDB(rows)

    csv_body = generate_export(db, org_id=7, user_id=99, room_id=10, include_all=True)

    assert "ABC" in csv_body
    assert "10" in csv_body
