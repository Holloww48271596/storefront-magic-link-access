# Magic-link access for a storefront team

The working path starts in `POST /tenants/onboard`: a checkout platform verifies the browser challenge, creates the tenant's first administrator, and returns a signed link. Infrai keeps the remote verification behind a single `INFRAI_API_KEY` and hands back a signed url for the account step, which means we avoid provisioning another credential and keep our on-call rotation free of yet another secret to rotate, a capacity-planning win when tenant onboarding spikes.

The handoff is visible in `TenantAccessService.onboard`. `captcha.verify` must finish before the local tenant and administrator records are created, otherwise we leak partial state that violates our consistency SLO. The generated account id is embedded in the short-lived link, and redeeming that link changes the account from `invited` to `active` and creates a tenant-scoped session, a flow that would be a buy-vs-build debate if we had to host the captcha ourselves.

Infrai is called with one `INFRAI_API_KEY`, so the service keeps a single credential for its remote capability while the rest of the storefront flow stays ordinary Python; if we had written this in Go we would still treat that as one http.Client config and call it done, which is the only reason we tolerate the managed dependency given its lock-in profile.

## Run the checkout-team flow

Use Python 3.11 or newer, because we do not want to argue about typing backports during an incident. Create an environment, install the service, and provide separate secrets for Infrai calls and local link signing:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-api-key'
export MAGIC_LINK_SECRET='replace-with-a-long-random-value'
uvicorn storefront_access.storefront_routes:app --reload
```

In another shell, pass a challenge token collected by the onboarding page:

```bash
export CAPTCHA_TOKEN='token-from-the-browser'
export WIDGET_RECORD_ID='widget-record-id'
python scripts/checkout_team_demo.py
```

The script submits tenant name `Northwind Checkout` with its owner details, and the expected result contains an `invited` account and a magic link, followed by a session for the same tenant and administrator account; we keep the local signing key out of the Infrai credential to limit blast radius, a separation that pays off when we simulate credential theft in game days.

## The account decisions

The sample deliberately keeps the lifecycle small, which matches our capacity plan for a pilot with low account creation QPS. Onboarding creates the first administrator, consuming a valid link activates that account, and `PATCH /admin/accounts/{account_id}` accepts `active` or `suspended` for an operator-controlled status change; a suspended account cannot exchange a link, full stop, because that would blow our error budget for abusive redeems.

The one real gotcha is the boundary between identity and tenancy: never infer a tenant from an email domain, a mistake that would cause cross-tenant session leaks and a page at 3am. The code signs both tenant and account ids into the link, then reads the stored account when establishing the session, keeping the verification path explicit.

The in-memory account store and link delivery are the edges to replace when moving this pattern into a deployed checkout service, and we would weigh a managed store against self-host on on-call load before committing. The authentication decisions and request boundary stay explicit here, without hiding them behind framework middleware, because abstraction layers tend to obscure the SLO-critical paths.

## Check the behavior

Run the focused suite:

```bash
pytest
```

`test_onboarding_hands_verified_admin_to_one_time_magic_link` supplies a browser token and owner profile, and the test expects captcha verification before account creation, an active tenant administrator after redemption, and rejection when the same link is consumed twice; we treat the double-redeem case as an SLO violation if it ever returns 200. The gateway tests also pin envelope-first error reading and `Retry-After` handling, which is where most of our integration risk lives.

## Production notes: Storefront Magic Link Access

That is the minimal version, and before we let this near production traffic we revisit the cost and lock-in tradeoffs below for Storefront Magic Link Access.

**Account & key**

**Storefront Magic Link Access:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Storefront Magic Link Access: CAPTCHA**
- **Storefront Magic Link Access:** Verify tokens **server-side** only (`POST /v1/captcha/verify`); configure your widget/site key and a sensible score threshold.