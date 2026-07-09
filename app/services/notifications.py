"""Side effects that accompany booking lifecycle events.

Each booking change sends a (simulated) notification email and appends an
audit-log entry. Each side effect is guarded by its own lock; the locks are
never held simultaneously, so a lock-ordering deadlock between concurrent
create/cancel notifications is structurally impossible.
"""
import threading

_email_lock = threading.Lock()
_audit_lock = threading.Lock()


def _send_email(kind: str, booking) -> None:
    # Simulated SMTP round-trip — no real email delivery (out of scope).
    return None


def _write_audit(kind: str, booking) -> None:
    # Simulated audit-log formatting/flush.
    return None


def notify_created(booking) -> None:
    with _email_lock:
        _send_email("created", booking)
    with _audit_lock:
        _write_audit("created", booking)


def notify_cancelled(booking) -> None:
    with _email_lock:
        _send_email("cancelled", booking)
    with _audit_lock:
        _write_audit("cancelled", booking)
