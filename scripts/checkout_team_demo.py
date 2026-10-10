from __future__ import annotations

import json
import os

import httpx


def main() -> None:
    base = os.environ.get("STOREFRONT_ACCESS_URL", "http://localhost:8000")
    onboarding = httpx.post(
        f"{base}/tenants/onboard",
        json={
            "tenant_name": "Northwind Checkout",
            "admin_email": "owner@example.com",
            "admin_name": "Store Owner",
            "widget_record_id": os.environ["WIDGET_RECORD_ID"],
            "captcha_token": os.environ["CAPTCHA_TOKEN"],
        },
        timeout=15.0,
    )
    onboarding.raise_for_status()
    invited = onboarding.json()

    token = invited["magic_link"].split("token=", maxsplit=1)[1]
    signed_in = httpx.post(
        f"{base}/sessions/magic-link", json={"token": token}, timeout=15.0
    )
    signed_in.raise_for_status()
    print(json.dumps({"onboarding": invited, "session": signed_in.json()}, indent=2))


if __name__ == "__main__":
    main()
