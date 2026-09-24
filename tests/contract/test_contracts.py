import unittest

from specromancy.contracts import CONTRACT_NAMES, load_contract, validate_contracts
from specromancy.errors import ExitCode


class ContractTests(unittest.TestCase):
    def test_all_contracts_load_from_package_resources(self) -> None:
        for name in CONTRACT_NAMES:
            with self.subTest(contract=name):
                self.assertIsInstance(load_contract(name), dict)

    def test_contract_versions_agree(self) -> None:
        versions = validate_contracts()
        self.assertEqual(versions.pipeline, "1")
        self.assertEqual(versions.schema, "1")
        self.assertEqual(versions.run_manifest_schema, "1")
        self.assertEqual(versions.artifact_schema, "1")
        self.assertEqual(versions.adapter_manifest, 1)

    def test_python_exit_codes_match_packaged_contract(self) -> None:
        rows = load_contract("exit-codes.json")["exit_codes"]
        expected = {row["name"]: row["code"] for row in rows}
        actual = {member.name: int(member) for member in ExitCode}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
