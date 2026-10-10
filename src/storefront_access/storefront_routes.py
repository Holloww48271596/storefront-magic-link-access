from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from .infrai_gateway import InfraiError, InfraiGateway, InfraiTransportError
from .tenant_access import (
    AccountStatusChange,
    MagicLinkExchange,
    SessionResult,
    TenantAccessService,
    TenantOnboardingRequest,
    TenantOnboardingResult,
)


def create_app(service: TenantAccessService | None = None) -> FastAPI:
    access = service or TenantAccessService(
        InfraiGateway(), os.environ["MAGIC_LINK_SECRET"]
    )
    api = FastAPI(title="Storefront team access")

    @api.post("/tenants/onboard", response_model=TenantOnboardingResult, status_code=201)
    def onboard_tenant(request: TenantOnboardingRequest) -> TenantOnboardingResult:
        try:
            return access.onboard(request)
        except InfraiError as exc:
            status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        except InfraiTransportError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @api.post("/sessions/magic-link", response_model=SessionResult)
    def exchange_magic_link(request: MagicLinkExchange) -> SessionResult:
        try:
            return access.exchange_magic_link(request.token)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @api.patch("/admin/accounts/{account_id}")
    def change_account_status(
        account_id: str, request: AccountStatusChange
    ) -> dict[str, str]:
        try:
            return asdict(access.set_account_status(account_id, request.status))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Account was not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return api


app = create_app()
