"""Composite scoring plus intent routing. Speculative heads stay in caller code."""

from __future__ import annotations

from jevsor import Client, Choice, Noul, Score, route_band


def main() -> int:
    state = {
        "message": "Approve the pending $12,000 withdrawal to a new beneficiary.",
        "user_role": "member",
    }
    with Client(provider="stub", fanout="isolated") as client:
        result = client.evaluate(
            state=state,
            questions={
                "intent": Choice(
                    "What is the user trying to do?",
                    {
                        "check_balance": "View account balance",
                        "approve_transfer": "Approve a withdrawal",
                        "support": "Get help",
                    },
                ),
                "risk": Score("Risk of acting automatically", ["Low", "Medium", "High"]),
                "clear": Noul("Is the request unambiguous?"),
            },
        )
    intent = result.answers["intent"]
    risk = result.answers["risk"]
    # Combine in code: high-stakes intent needs a higher confidence bar.
    high_stakes = intent.choice == "approve_transfer"
    bar = 0.9 if high_stakes else 0.6
    if intent.confidence < bar or risk.score >= 1.5:
        action = "route_to_human"
    elif route_band(intent.confidence) == "act":
        action = intent.choice
    else:
        action = "confirm"
    print(action, intent.choice, intent.confidence, risk.score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
