from datetime import datetime, timedelta, timezone
import unittest

from specromancy.clock import FixedClock, RunIdGenerator, utc_timestamp


class ClockTests(unittest.TestCase):
    def test_timestamp_is_stable_utc(self) -> None:
        instant = datetime(2026, 9, 20, 12, 34, 56, 789, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(utc_timestamp(instant), "2026-09-20T10:34:56Z")

    def test_run_id_is_deterministic_with_injected_clock_and_token(self) -> None:
        generator = RunIdGenerator(
            clock=FixedClock(datetime(2026, 9, 20, tzinfo=timezone.utc)),
            token_factory=lambda: "ABC123",
        )
        self.assertEqual(
            generator.generate("Add durable state!"),
            "20260920-add-durable-state-abc123",
        )

    def test_fixed_clock_rejects_naive_datetime(self) -> None:
        with self.assertRaises(ValueError):
            FixedClock(datetime(2026, 9, 20))


if __name__ == "__main__":
    unittest.main()

