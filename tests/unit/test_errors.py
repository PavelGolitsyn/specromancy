import unittest

from specromancy.errors import (
    ApprovalRequiredError,
    ConcurrencyError,
    ExitCode,
    ExternalCommandError,
    InvalidInputError,
    InvalidTransitionError,
    SafetyError,
    ValidationError,
    normalize_exception,
)


class ErrorTests(unittest.TestCase):
    def test_exception_types_map_to_reserved_exit_codes(self) -> None:
        cases = (
            (InvalidInputError("bad"), ExitCode.INVALID_INPUT),
            (InvalidTransitionError("bad"), ExitCode.INVALID_TRANSITION),
            (ValidationError("bad"), ExitCode.VALIDATION_FAILED),
            (ApprovalRequiredError("bad"), ExitCode.APPROVAL_REQUIRED),
            (ExternalCommandError("bad"), ExitCode.EXTERNAL_COMMAND_FAILED),
            (SafetyError("bad"), ExitCode.SAFETY_REJECTED),
            (ConcurrencyError("bad"), ExitCode.CONCURRENCY_CONFLICT),
        )
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(error.exit_code, expected)

    def test_error_dictionary_matches_contract_shape(self) -> None:
        error = SafetyError("unsafe", hint="choose another path", path="../outside")
        self.assertEqual(
            set(error.as_dict()),
            {"code", "message", "hint", "path", "retryable", "details"},
        )

    def test_os_errors_are_normalized_without_tracebacks(self) -> None:
        error = normalize_exception(OSError("disk unavailable"))
        self.assertIsInstance(error, ValidationError)
        self.assertIn("disk unavailable", error.message)


if __name__ == "__main__":
    unittest.main()

