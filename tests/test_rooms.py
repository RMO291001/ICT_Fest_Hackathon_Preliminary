from datetime import datetime

from app.routers.rooms import room_stats
from app.services import stats


def test_room_stats_uses_database_aggregation():
    stats._stats.clear()

    class DummyBooking:
        def __init__(self, room_id, status, price_cents):
            self.room_id = room_id
            self.status = status
            self.price_cents = price_cents

    class DummyQuery:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return DummyRoom()

        def one(self):
            return (2, 1500)

    class DummyDB:
        def __init__(self):
            self.queries = []

        def query(self, *args, **kwargs):
            self.queries.append((args, kwargs))
            return DummyQuery([])

    class DummyRoom:
        def __init__(self):
            self.id = 42

    room = DummyRoom()
    db = DummyDB()

    class DummyUser:
        org_id = 7

    result = room_stats(room.id, db=db, user=DummyUser())

    assert result == {
        "room_id": 42,
        "total_confirmed_bookings": 2,
        "total_revenue_cents": 1500,
    }
