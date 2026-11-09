"""Thin PayPal Orders v2 client using plain `requests` (no PayPal SDK)."""
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

TIMEOUT = 15  # seconds, so a slow PayPal never hangs our server

# Access token cache (module-level, one token shared by all requests)
_token = {"value": None, "expires_at": 0.0}


class PayPalError(Exception):
    """Raised when PayPal is unreachable or returns a non-2xx response."""


def _base_url():
    # Sandbox by default; set PAYPAL_BASE_URL in .env to change it
    return os.environ.get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")


def _json_or_raise(resp, what):
    """Return parsed JSON on 2xx, otherwise log PayPal's error body and raise."""
    if resp.ok:
        return resp.json()
    # PayPal's error body has the reason and a debug_id (no secrets in it)
    log.error("PayPal %s failed: HTTP %s %s", what, resp.status_code, resp.text)
    raise PayPalError(f"PayPal {what} failed (HTTP {resp.status_code})")


def get_access_token():
    """Get an OAuth token, reusing the cached one until shortly before it expires."""
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]

    client_id = os.environ.get("PAYPAL_CLIENT_ID")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise PayPalError("PayPal credentials are missing from the environment")

    try:
        resp = requests.post(
            f"{_base_url()}/v1/oauth2/token",
            auth=(client_id, client_secret),  # HTTP basic auth
            data={"grant_type": "client_credentials"},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        log.error("PayPal token request error: %s", type(e).__name__)
        raise PayPalError("Could not reach PayPal") from e

    data = _json_or_raise(resp, "token request")
    _token["value"] = data["access_token"]
    # Refresh 60 seconds early so we never send an expired token
    _token["expires_at"] = time.time() + data["expires_in"] - 60
    return _token["value"]


def _post(path, body, request_id, what):
    """POST to PayPal with bearer token and the idempotency header."""
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "PayPal-Request-Id": request_id,  # same id on a retry = same result
    }
    try:
        resp = requests.post(
            f"{_base_url()}{path}", json=body, headers=headers, timeout=TIMEOUT
        )
    except requests.RequestException as e:
        log.error("PayPal %s error: %s", what, type(e).__name__)
        raise PayPalError("Could not reach PayPal") from e
    return _json_or_raise(resp, what)


def create_order(amount_str, currency, custom_id, request_id):
    """Create a CAPTURE order. amount_str looks like "60.00"."""
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "custom_id": custom_id,  # our milestone id
                "amount": {"currency_code": currency, "value": amount_str},
            }
        ],
    }
    return _post("/v2/checkout/orders", body, request_id, "create order")


def capture_order(order_id, request_id):
    """Capture an order the buyer has approved."""
    return _post(f"/v2/checkout/orders/{order_id}/capture", {}, request_id, "capture order")


def read_capture(capture_response):
    """Pull the first capture out of PayPal's response.

    Returns a dict (order_status, status, capture_id, value, currency),
    or None if the response does not have the expected shape.
    """
    try:
        cap = capture_response["purchase_units"][0]["payments"]["captures"][0]
        return {
            "order_status": capture_response["status"],
            "status": cap["status"],
            "capture_id": cap["id"],
            "value": cap["amount"]["value"],
            "currency": cap["amount"]["currency_code"],
        }
    except (KeyError, IndexError, TypeError):
        return None
