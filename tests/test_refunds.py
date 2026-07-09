from app.services.refunds import compute_refund_cents


def test_compute_refund_cents_uses_integer_half_up_rounding():
    assert compute_refund_cents(999, 50) == 500
    assert compute_refund_cents(1001, 50) == 501
