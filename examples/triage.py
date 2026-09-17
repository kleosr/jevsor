"""Fan-out plus confidence bands. Offline via stub."""

from __future__ import annotations

from jevsor import Client, Choice, Noul, Score, route_band


def main() -> int:
    state = {
        "ticket": "Help! My payouts have been failing for 3 days.",
        "account_age_days": 800,
    }
    with Client(provider="stub", fanout="isolated") as client:
        result = client.evaluate(
            state=state,
            questions={
                "dept": Choice(
                    "Which team should handle this?",
                    {
                        "billing": "Payments, invoicing, refunds",
                        "tech": "Bugs, outages, integrations",
                        "sales": "Pricing, upgrades, new accounts",
                    },
                ),
                "urgent": Noul(
                    "Does this convey urgency?",
                    {"true": "Time-sensitive", "false": "No urgency"},
                ),
                "heat": Score("How frustrated is the customer?", ["Calm", "Frustrated", "Furious"]),
            },
        )
    dept = result.answers["dept"]
    band = route_band(dept.confidence)
    print(dept.choice, band, result.answers["urgent"].noul, result.answers["heat"].score)
    if band == "human":
        print("route to human")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
