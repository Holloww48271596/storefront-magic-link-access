from __future__ import annotations

import pytest

from storefront_access.tenant_access import TenantAccessService, TenantOnboardingRequest


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def verify_captcha(self, widget_record_id: str, token: str) -> dict[str, object]:
        self.calls.append(("captcha", widget_record_id, token))
        return {"verified": True}


def test_onboarding_hands_verified_admin_to_one_time_magic_link() -> None:
    provider = RecordingProvider()
    service = TenantAccessService(provider, "test-signing-secret")
    invited = service.onboard(
        TenantOnboardingRequest(
            tenant_name="Northwind Checkout",
            admin_email="owner@example.com",
            admin_name="Store Owner",
            widget_record_id="widget-record",
            captcha_token="browser-proof",
        )
    )

    session = service.exchange_magic_link(invited.magic_link.split("token=")[1])

    assert provider.calls == [("captcha", "widget-record", "browser-proof")]
    assert session.account_id.startswith("account_")
    assert session.tenant_id == invited.tenant_id
    assert session.role == "admin"
    assert service.accounts[session.account_id].status == "active"
    with pytest.raises(ValueError, match="already been used"):
        service.exchange_magic_link(invited.magic_link.split("token=")[1])
