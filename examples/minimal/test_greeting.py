import unittest

from greeting import greet


class GreetingTests(unittest.TestCase):
    def test_greets_a_name(self) -> None:
        self.assertEqual(greet("Ada"), "Hello, Ada!")

    def test_trims_surrounding_whitespace(self) -> None:
        self.assertEqual(greet("  Ada  "), "Hello, Ada!")

    def test_rejects_a_blank_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "name must not be blank"):
            greet("   ")


if __name__ == "__main__":
    unittest.main()
