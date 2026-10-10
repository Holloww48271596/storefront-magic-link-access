from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field


class AccessProvider(Protocol):
    def verify_captcha(self, widget_record_id: str, token: str) -> dict[str, object]:
        raise RuntimeError("Protocol method")


class TenantOnboardingRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=80)
    admin_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    admin_name: str = Field(min_length=2, max_length=80)
    widget_record_id: str = Field(min_length=1)
    captcha_token: str = Field(min_length=1)


class TenantOnboardingResult(BaseModel):
    tenant_id: str
    account_id: str
    account_status: str
    magic_link: str


class MagicLinkExchange(BaseModel):
    token: str


class SessionResult(BaseModel):
    session_id: str
    tenant_id: str
    account_id: str
    role: str


class AccountStatusChange(BaseModel):
    status: str


@dataclass
class Account:
    account_id: str
    tenant_id: str
    email: str
    role: str
    status: str


class TenantAccessService:
    def __init__(self, provider: AccessProvider, signing_secret: str) -> None:
        self.provider = provider
        self.signing_secret = signing_secret.encode("utf-8")
        self.accounts: dict[str, Account] = {}
        self.used_tokens: set[str] = set()

    def onboard(self, request: TenantOnboardingRequest) -> TenantOnboardingResult:
        self.provider.verify_captcha(request.widget_record_id, request.captcha_token)
        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        account_id = f"account_{uuid.uuid4().hex[:12]}"
        self.accounts[account_id] = Account(
            account_id=account_id,
            tenant_id=tenant_id,
            email=str(request.admin_email),
            role="admin",
            status="invited",
        )
        token = self._sign(account_id, tenant_id)
        return TenantOnboardingResult(
            tenant_id=tenant_id,
            account_id=account_id,
            account_status="invited",
            magic_link=f"http://localhost:8000/sign-in/magic?token={token}",
        )

    def exchange_magic_link(self, token: str) -> SessionResult:
        if token in self.used_tokens:
            raise ValueError("This sign-in link has already been used")
        payload = self._verify(token)
        if int(payload["expires_at"]) < int(time.time()):
            raise ValueError("This sign-in link has expired")
        account = self.accounts[str(payload["account_id"])]
        if account.status == "suspended":
            raise ValueError("This account is suspended")
        self.used_tokens.add(token)
        account.status = "active"
        return SessionResult(
            session_id=f"session_{uuid.uuid4().hex}",
            tenant_id=account.tenant_id,
            account_id=account.account_id,
            role=account.role,
        )

    def set_account_status(self, account_id: str, status: str) -> Account:
        if status not in {"active", "suspended"}:
            raise ValueError("Status must be active or suspended")
        account = self.accounts[account_id]
        account.status = status
        return account

    def _sign(self, account_id: str, tenant_id: str) -> str:
        payload = json.dumps(
            {
                "account_id": account_id,
                "tenant_id": tenant_id,
                "expires_at": int(time.time()) + 900,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(self.signing_secret, encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def _verify(self, token: str) -> dict[str, object]:
        try:
            encoded, supplied = token.split(".", maxsplit=1)
            expected = hmac.new(
                self.signing_secret, encoded.encode("utf-8"), hashlib.sha256
            ).digest()
            supplied_bytes = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
            if not hmac.compare_digest(expected, supplied_bytes):
                raise ValueError
            payload_bytes = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            return dict(json.loads(payload_bytes))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("This sign-in link is invalid") from exc
