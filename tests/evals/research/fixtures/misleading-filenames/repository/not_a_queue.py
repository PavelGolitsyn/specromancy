"""Despite the filename, this module owns notification retry behavior."""

RETRY_DELAY_SECONDS = 5


def next_notification_delay(attempt: int) -> int:
    return RETRY_DELAY_SECONDS * attempt
