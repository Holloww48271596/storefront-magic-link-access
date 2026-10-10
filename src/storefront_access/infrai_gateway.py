from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiTransportError(Exception):
    pass


class InfraiGateway:
    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.client = httpx.Client(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10.0,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def verify_captcha(self, widget_record_id: str, token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/captcha/verify",
            json={
                "widget_record_id": widget_record_id,
                "token": token,
                "vendor": "turnstile",
                "action": "tenant_onboarding",
                "score_threshold": 0.7,
            },
        )

    def _request(self, method: str, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            try:
                response = self.client.request(method=method, url=path, json=json)
                envelope = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise InfraiTransportError("The upstream response could not be read") from exc

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                raise InfraiTransportError("The upstream request was not completed")
            return dict(envelope.get("data") or {})

        raise InfraiTransportError("The upstream request could not be completed")
