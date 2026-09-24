"""Tiny application used by the Specromancy release walkthrough."""


def greet(name: str) -> str:
    """Return a friendly greeting for a nonblank name."""

    normalized = name.strip()
    if not normalized:
        raise ValueError("name must not be blank")
    return f"Hello, {normalized}!"
