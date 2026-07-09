"""Refund bookkeeping.

Refund amount = percentage of price_cents, rounded to the nearest cent with
half-cents rounding up. Both the cancel response and the RefundLog call
compute_refund_cents so they can never disagree.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Booking, RefundLog


def compute_refund_cents(price_cents: int, percent: int) -> int:
    """Integer half-up rounding. No floats in money math, ever."""
    return (price_cents * percent + 50) // 100


def log_refund(db: Session, booking: Booking, percent: int) -> RefundLog:
    entry = RefundLog(
        booking_id=booking.id,
        amount_cents=compute_refund_cents(booking.price_cents, percent),
        status="processed",
        processed_at=datetime.utcnow(),
    )
    db.add(entry)  # no commit here — caller owns the transaction
    return entry