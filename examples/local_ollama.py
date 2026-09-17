"""Ollama local path. Falls back to stub so the example stays offline-green."""

from __future__ import annotations

from jevsor import Client, Noul


def main() -> int:
    questions = {"greeting": Noul("Is this a greeting?")}
    state = "hello there"
    try:
        with Client(provider="ollama", model="llama3.1", fanout="isolated") as client:
            result = client.evaluate(state=state, questions=questions)
            print("provider", result.debug.provider if result.debug else "ollama")
    except Exception as exc:
        print("ollama unavailable, using stub:", type(exc).__name__)
        with Client(provider="stub", fanout="isolated") as client:
            result = client.evaluate(state=state, questions=questions)
    print("noul", result.answers["greeting"].noul, result.answers["greeting"].provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
