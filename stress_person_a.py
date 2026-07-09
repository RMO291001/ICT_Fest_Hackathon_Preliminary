#!/usr/bin/env python3
"""Concurrency stress tests for Person A's bug fixes.

Run against the LIVE container at http://localhost:8000.
Tests: rate-limit race, reference-code uniqueness, refresh single-use race,
liveness/deadlock probe.
"""
import concurrent.futures
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "http://localhost:8000"
PASS_COUNT = 0
FAIL_COUNT = 0


def _uid(prefix: str) -> str:
    return f"{prefix}-{time.time()}-{id(object())}"


def _future_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()


def _register_and_login(org: str, user: str, pw: str = "pw12345"):
    requests.post(f"{BASE}/auth/register", json={
        "org_name": org, "username": user, "password": pw,
    })
    r = requests.post(f"{BASE}/auth/login", json={
        "org_name": org, "username": user, "password": pw,
    })
    data = r.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def check(name: str, passed: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    tag = "PASS" if passed else "FAIL"
    if not passed:
        FAIL_COUNT += 1
    else:
        PASS_COUNT += 1
    msg = f"  [{tag}] {name}"
    if detail and not passed:
        msg += f" — {detail}"
    print(msg)


# ═══════════════════════════════════════════════════════════════════════════
# 1. RATE-LIMIT RACE: 40 concurrent POST /bookings from one user
# ═══════════════════════════════════════════════════════════════════════════
def test_ratelimit_race():
    print("\n── Rate-limit race ──")
    org = _uid("rl-org")
    data, headers = _register_and_login(org, "rl-user")
    # Create a room
    r = requests.post(f"{BASE}/rooms", json={
        "name": "RL Room", "capacity": 10, "hourly_rate_cents": 100,
    }, headers=headers)
    room_id = r.json()["id"]

    def fire(i):
        # Each request uses a different time slot to avoid ROOM_CONFLICT
        start_h = 50 + i * 2
        return requests.post(f"{BASE}/bookings", json={
            "room_id": room_id,
            "start_time": _future_iso(start_h),
            "end_time": _future_iso(start_h + 1),
        }, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=40) as pool:
        futures = [pool.submit(fire, i) for i in range(40)]
        results = [f.result(timeout=15) for f in futures]

    codes = [r.status_code for r in results]
    ok = codes.count(201)
    limited = codes.count(429)
    check("20 succeed (non-429)", ok == 20, f"got {ok}")
    check("20 get 429", limited == 20, f"got {limited}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. REFERENCE-CODE UNIQUENESS: 15 users create bookings concurrently
# ═══════════════════════════════════════════════════════════════════════════
def test_reference_uniqueness():
    print("\n── Reference-code uniqueness ──")
    org = _uid("ref-org")
    # Register admin + 14 members
    users = []
    admin_data, admin_h = _register_and_login(org, "ref-admin")
    # Create a room
    r = requests.post(f"{BASE}/rooms", json={
        "name": "Ref Room", "capacity": 20, "hourly_rate_cents": 200,
    }, headers=admin_h)
    room_id = r.json()["id"]
    users.append(admin_h)
    for i in range(14):
        _, h = _register_and_login(org, f"ref-user-{i}")
        users.append(h)

    def create(idx):
        h = users[idx]
        start_h = 50 + idx * 2
        return requests.post(f"{BASE}/bookings", json={
            "room_id": room_id,
            "start_time": _future_iso(start_h),
            "end_time": _future_iso(start_h + 1),
        }, headers=h)

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
        futures = [pool.submit(create, i) for i in range(15)]
        results = [f.result(timeout=15) for f in futures]

    codes = [r.json().get("reference_code") for r in results if r.status_code == 201]
    check("all reference codes unique", len(codes) == len(set(codes)),
          f"{len(codes)} codes, {len(set(codes))} unique")


# ═══════════════════════════════════════════════════════════════════════════
# 3. REFRESH SINGLE-USE RACE: 8 concurrent refresh with same token
# ═══════════════════════════════════════════════════════════════════════════
def test_refresh_race():
    print("\n── Refresh single-use race ──")
    org = _uid("rr-org")
    data, _ = _register_and_login(org, "rr-user")
    refresh_token = data["refresh_token"]

    def do_refresh(_):
        return requests.post(f"{BASE}/auth/refresh", json={
            "refresh_token": refresh_token,
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(do_refresh, i) for i in range(8)]
        results = [f.result(timeout=10) for f in futures]

    statuses = [r.status_code for r in results]
    ok = statuses.count(200)
    denied = statuses.count(401)
    check("exactly 1 gets 200", ok == 1, f"got {ok}")
    check("rest get 401", denied == 7, f"got {denied}")


# ═══════════════════════════════════════════════════════════════════════════
# 4. LIVENESS/DEADLOCK PROBE: interleave creates + cancels, then /health
# ═══════════════════════════════════════════════════════════════════════════
def test_liveness():
    print("\n── Liveness / deadlock probe ──")
    org = _uid("lv-org")
    data, headers = _register_and_login(org, "lv-admin")
    # Create a room
    r = requests.post(f"{BASE}/rooms", json={
        "name": "LV Room", "capacity": 10, "hourly_rate_cents": 100,
    }, headers=headers)
    room_id = r.json()["id"]

    # Create 20 bookings sequentially (need IDs for cancellation)
    booking_ids = []
    for i in range(20):
        start_h = 50 + i * 2
        r = requests.post(f"{BASE}/bookings", json={
            "room_id": room_id,
            "start_time": _future_iso(start_h),
            "end_time": _future_iso(start_h + 1),
        }, headers=headers)
        if r.status_code == 201:
            booking_ids.append(r.json()["id"])

    # Now concurrently cancel the first 10 and create 10 more (new slots)
    def cancel(bid):
        return requests.post(f"{BASE}/bookings/{bid}/cancel", headers=headers)

    def create(idx):
        start_h = 100 + idx * 2
        return requests.post(f"{BASE}/bookings", json={
            "room_id": room_id,
            "start_time": _future_iso(start_h),
            "end_time": _future_iso(start_h + 1),
        }, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        cancel_futures = [pool.submit(cancel, bid) for bid in booking_ids[:10]]
        create_futures = [pool.submit(create, i) for i in range(10)]
        all_futures = cancel_futures + create_futures
        concurrent.futures.wait(all_futures, timeout=10)

    # Now immediately check /health with a 5s timeout
    start = time.time()
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        elapsed = time.time() - start
        check("/health returns 200", r.status_code == 200, f"got {r.status_code}")
        check("/health responds in <2s", elapsed < 2, f"took {elapsed:.2f}s")
    except requests.Timeout:
        check("/health responds in <2s", False, "timed out after 5s — possible deadlock")


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_ratelimit_race()
    test_reference_uniqueness()
    test_refresh_race()
    test_liveness()
    print(f"\n{'='*60}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    if FAIL_COUNT > 0:
        sys.exit(1)
    print("ALL CHECKS PASSED")
