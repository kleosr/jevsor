"""Labeled System One holdout. Ground truth is in the state, not model agreement."""

from __future__ import annotations

from typing import Any

from jevsor.contract import Choice, Noul, Score

DEPTS = {
    "billing": "Payments, invoicing, refunds",
    "technical": "Bugs, outages, integrations",
    "sales": "Pricing, upgrades, new accounts",
}

BILLING = [
    "Refund the duplicate $49 charge on invoice {n}.",
    "My card was billed twice for order {n}. Please credit the extra charge.",
    "Where do I download invoices for last month? Account {n}.",
    "Subscription renewal charged me after I cancelled. Invoice {n}.",
    "Need a copy of the receipt for payment {n}.",
    "Chargeback opened on settlement {n}.",
    "VAT invoice missing for payment {n}.",
]
TECH = [
    "API POST /v1/pay returns 502 after deploy {n}.",
    "Webhook deliveries fail with timeout to endpoint {n}.",
    "SSO login loops after enabling SAML on tenant {n}.",
    "The dashboard chart is blank since we upgraded worker {n}.",
    "SDK throws TypeError on checkout in build {n}.",
    "Health check on replica {n} is failing.",
    "Rate limiter 429s every request on route {n}.",
]
SALES = [
    "Can we get a quote for 200 seats on plan {n}?",
    "We want to upgrade from starter to business. Account {n}.",
    "Is annual billing cheaper than monthly for org {n}?",
    "Please have someone walk us through enterprise pricing. Ref {n}.",
    "We're comparing you to a competitor for RFP {n}.",
    "Can we add a nonprofit discount on account {n}?",
    "Book a demo for team {n} next week.",
]
URGENT = [
    "This is blocking production. Need this today.",
    "ASAP — customers cannot check out.",
    "Pager is firing. Please treat as P1.",
]
CALM = [
    "No rush, whenever you have a moment.",
    "Just checking when you get a chance.",
    "FYI only, not urgent.",
]


def _questions() -> dict[str, Any]:
    return {
        "department": Choice("Which team should handle this?", DEPTS),
        "is_urgent": Noul("Does this convey urgency?"),
        "frustration": Score(
            "How frustrated is the customer?",
            ["Calm", "Frustrated", "Very angry"],
        ),
    }


def cases() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = 0
    for dept, templates in (("billing", BILLING), ("technical", TECH), ("sales", SALES)):
        for i, tmpl in enumerate(templates):
            for urgent, extra in ((True, URGENT[i % len(URGENT)]), (False, CALM[i % len(CALM)])):
                for heat, heat_txt in ((0, "Thanks."), (1, "This is getting frustrating."), (2, "I am furious.")):
                    n += 1
                    ticket = f"{tmpl.format(n=1000 + n)} {extra} {heat_txt}"
                    out.append(
                        {
                            "id": f"{dept[:4]}-{n:03d}",
                            "state": {"ticket": ticket, "account": 1000 + n},
                            "questions": _questions(),
                            "labels": {
                                "department": {"choice": dept},
                                "is_urgent": {"noul_true": urgent},
                                "frustration": {"score": heat},
                            },
                        }
                    )
    return out
