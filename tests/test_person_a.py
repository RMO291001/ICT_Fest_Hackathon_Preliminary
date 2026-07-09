"""Person A bug-fix verification tests.

Covers: auth token lifetime (B-06), logout (B-05), refresh single-use (B-05),
register duplicate username (B-01/B-02), org admin/member assignment,
and timezone offset conversion (B-32).

Every test uses a FRESH org/user to avoid rate-limiter or quota interference.
Booking start times are >24h in the future to avoid quota-window issues.
"""
import time as _time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.main import app
from app.config import JWT_SECRET, JWT_ALGORITHM

client = TestClient(app)


def _unique(prefix: str) -> str:
    return f"{prefix}-{_time.time()}-{id(object())}"


def _register_and_login(org_name: str, username: str, password: str = "pw12345"):
    """Register a user and return (login_response_json, headers)."""
    client.post("/auth/register", json={
        "org_name": org_name, "username": username, "password": password,
    })
    login = client.post("/auth/login", json={
        "org_name": org_name, "username": username, "password": password,
    })
    data = login.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def _future(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()


# ── B-06: access token lifetime must be exactly 900 seconds ──────────────
def test_access_token_lifetime_is_900s():
    org = _unique("lt-org")
    data, _ = _register_and_login(org, "alice")
    payload = jwt.decode(data["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["exp"] - payload["iat"] == 900
    assert "sub" in payload and isinstance(payload["sub"], str)
    assert "org" in payload
    assert "role" in payload
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload
    assert payload["type"] == "access"


# ── B-05: logout invalidates the presented token ────────────────────────
def test_logout_invalidates_presented_token():
    org = _unique("lo-org")
    data, headers = _register_and_login(org, "bob")
    # Verify token works before logout
    r = client.get("/rooms", headers=headers)
    assert r.status_code == 200
    # Logout
    r = client.post("/auth/logout", headers=headers)
    assert r.status_code == 200
    # Same token should now be rejected
    r = client.get("/rooms", headers=headers)
    assert r.status_code == 401


# ── B-05: refresh rotates and is single-use ──────────────────────────────
def test_refresh_rotates_and_is_single_use():
    org = _unique("rf-org")
    data, _ = _register_and_login(org, "carol")
    old_refresh = data["refresh_token"]
    # First refresh: should succeed
    r1 = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200
    new_data = r1.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data
    assert new_data["refresh_token"] != old_refresh
    # Second refresh with OLD token: should fail
    r2 = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


# ── B-05: refresh rejects access token ───────────────────────────────────
def test_refresh_rejects_access_token_as_refresh_token():
    org = _unique("ra-org")
    data, _ = _register_and_login(org, "dave")
    r = client.post("/auth/refresh", json={"refresh_token": data["access_token"]})
    assert r.status_code == 401


# ── B-01/B-02: duplicate username returns 409 ───────────────────────────
def test_register_duplicate_username_returns_409():
    org = _unique("dup-org")
    r1 = client.post("/auth/register", json={
        "org_name": org, "username": "eve", "password": "pw12345",
    })
    assert r1.status_code == 201
    r2 = client.post("/auth/register", json={
        "org_name": org, "username": "eve", "password": "pw99999",
    })
    assert r2.status_code == 409
    assert r2.json()["code"] == "USERNAME_TAKEN"


# ── B-01/B-02: first user is admin, second is member ────────────────────
def test_register_new_org_is_admin_join_is_member():
    org = _unique("am-org")
    r1 = client.post("/auth/register", json={
        "org_name": org, "username": "admin1", "password": "pw12345",
    })
    assert r1.status_code == 201
    assert r1.json()["role"] == "admin"
    r2 = client.post("/auth/register", json={
        "org_name": org, "username": "member1", "password": "pw12345",
    })
    assert r2.status_code == 201
    assert r2.json()["role"] == "member"


# ── B-32: offset datetime converted, not discarded ──────────────────────
def test_offset_datetime_converted_not_discarded():
    org = _unique("tz-org")
    # Register admin, login, create room
    client.post("/auth/register", json={
        "org_name": org, "username": "tzadmin", "password": "pw12345",
    })
    login = client.post("/auth/login", json={
        "org_name": org, "username": "tzadmin", "password": "pw12345",
    })
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    room = client.post("/rooms", json={
        "name": "TZ Room", "capacity": 4, "hourly_rate_cents": 500,
    }, headers=headers)
    assert room.status_code == 201
    room_id = room.json()["id"]

    # POST booking with +06:00 offset — must be stored as UTC
    # Use a start_time far enough in the future
    start_with_offset = "2026-12-01T10:00:00+06:00"
    end_with_offset = "2026-12-01T12:00:00+06:00"
    booking = client.post("/bookings", json={
        "room_id": room_id,
        "start_time": start_with_offset,
        "end_time": end_with_offset,
    }, headers=headers)
    assert booking.status_code == 201
    bdata = booking.json()
    # "2026-12-01T10:00:00+06:00" in UTC is "2026-12-01T04:00:00+00:00"
    assert bdata["start_time"].startswith("2026-12-01T04:00:00")
    assert bdata["end_time"].startswith("2026-12-01T06:00:00")
