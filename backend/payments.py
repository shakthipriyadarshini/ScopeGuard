"""Payment endpoints. The amount ALWAYS comes from the database, never the browser."""
import threading
import uuid
from decimal import Decimal
from functools import wraps

from flask import Blueprint, jsonify, request

from app.models import Milestone, Payment, SessionLocal
from app.routes.auth import can_pay
from app.services import paypal_service
from app.services.paypal_service import PayPalError

bp = Blueprint("payments", __name__, url_prefix="/api/payments")

CURRENCY = "USD"


def _error(message, code):
    return jsonify({"error": message}), code


def _get_json():
    """JSON body as a dict. Anything else (list, string, bad JSON) counts as empty."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# Only one capture runs at a time (per server process). Without this, two
# approved orders for the same milestone could both pass the "not PAID yet"
# check and both take money. The DB session is opened AFTER the lock is held,
# so every capture reads fresh data.
_capture_lock = threading.Lock()


def _one_at_a_time(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        with _capture_lock:
            return view(*args, **kwargs)

    return wrapped


@bp.post("/create-order")
def create_order():
    # We only read the milestone id from the request, nothing else
    data = _get_json()
    try:
        milestone_id = int(data.get("milestone_id"))
    except (TypeError, ValueError):
        return _error("milestone_id is required", 400)

    with SessionLocal() as db:
        milestone = db.get(Milestone, milestone_id)
        # Same 404 whether it is missing or not yours, so ids cannot be probed
        if milestone is None or not can_pay(milestone):
            return _error("Milestone not found", 404)
        if milestone.status == "PAID":
            return _error("Milestone is already paid", 409)

        # Amount comes from the DB (integer cents), sent to PayPal as a string
        amount_str = milestone.amount_str
        request_id = str(uuid.uuid4())

        try:
            order = paypal_service.create_order(
                amount_str, CURRENCY, str(milestone.id), request_id
            )
        except PayPalError:
            return _error("Could not create the PayPal order", 502)

        # Remember the order so capture can find it later
        db.add(
            Payment(
                milestone_id=milestone.id,
                paypal_order_id=order["id"],
                amount_cents=milestone.amount_cents,
                currency=CURRENCY,
                status="CREATED",
                request_id=request_id,
            )
        )
        db.commit()

    return jsonify({"id": order["id"]})


@bp.post("/capture-order")
@_one_at_a_time
def capture_order():
    data = _get_json()
    order_id = data.get("order_id")
    if not order_id or not isinstance(order_id, str):
        return _error("order_id is required", 400)

    with SessionLocal() as db:
        # Only orders we created are accepted
        payment = db.query(Payment).filter_by(paypal_order_id=order_id).first()
        if payment is None:
            return _error("Unknown order", 404)

        milestone = db.get(Milestone, payment.milestone_id)
        if not can_pay(milestone):
            return _error("You are not allowed to pay this milestone", 403)

        # Idempotent: capturing twice just reports success
        if payment.status == "CAPTURED":
            return jsonify({"status": "CAPTURED", "milestone_id": milestone.id})
        if payment.status != "CREATED":
            return _error("This payment can no longer be captured", 409)
        if milestone.status == "PAID":
            # Another order already paid this milestone: never charge twice
            return _error("Milestone is already paid", 409)

        # Capture. The capture request id is derived from the payment's id,
        # so a retry of the same capture is safe on PayPal's side too.
        try:
            result = paypal_service.capture_order(
                order_id, "capture-" + payment.request_id
            )
        except PayPalError:
            # Payment stays CREATED so the buyer can retry
            return _error("PayPal could not capture the payment", 502)

        # Verify status, currency and amount against OUR database
        info = paypal_service.read_capture(result)
        expected = Decimal(milestone.amount_cents) / 100
        verified = (
            info is not None
            and info["order_status"] == "COMPLETED"
            and info["status"] == "COMPLETED"
            and info["currency"] == payment.currency == CURRENCY
            and Decimal(info["value"]) == expected
        )

        if not verified:
            payment.status = "FAILED"
            db.commit()
            return _error("Payment verification failed", 400)

        # ONE transaction: payment and milestone change together (single commit)
        payment.status = "CAPTURED"
        payment.capture_id = info["capture_id"]
        milestone.status = "PAID"
        db.commit()

        return jsonify({"status": "CAPTURED", "milestone_id": milestone.id})


@bp.get("/status/<int:milestone_id>")
def payment_status(milestone_id):
    with SessionLocal() as db:
        milestone = db.get(Milestone, milestone_id)
        if milestone is None or not can_pay(milestone):
            return _error("Milestone not found", 404)

        # Latest payment attempt for this milestone (if any)
        payment = (
            db.query(Payment)
            .filter_by(milestone_id=milestone_id)
            .order_by(Payment.id.desc())
            .first()
        )
        return jsonify(
            {
                "milestone_id": milestone.id,
                "milestone_status": milestone.status,
                "payment_status": payment.status if payment else None,
            }
        )
