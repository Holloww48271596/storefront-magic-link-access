from __future__ import annotations

import json

import httpx
import pytest

from storefront_access.infrai_gateway import InfraiError, InfraiGateway


def test_business_rejection_is_read_from_envelope_before_status() -> None:
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "ok": False,
                "data": None,
                "error": {"code": "CHECK_REJECTED", "message": "Try the check again"},
                "metadata": {},
            },
        )

    gateway = InfraiGateway(api_key="test-key", transport=httpx.MockTransport(reject))
    with pytest.raises(InfraiError) as raised:
        gateway.verify_captcha("widget-record", "browser-proof")

    assert raised.value.code == "CHECK_REJECTED"
    assert raised.value.status_code == 422


def test_rate_limit_honours_retry_after() -> None:
    sleeps: list[float] = []
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        assert request.url.path == "/v1/captcha/verify"
        assert json.loads(request.content)["widget_record_id"] == "widget-record"
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={"ok": False, "data": None, "error": {}, "metadata": {}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"verified": True}, "error": None, "metadata": {}},
        )

    gateway = InfraiGateway(
        api_key="test-key", transport=httpx.MockTransport(respond), sleep=sleeps.append
    )
    assert gateway.verify_captcha("widget-record", "browser-proof") == {"verified": True}
    assert sleeps == [2.0]
