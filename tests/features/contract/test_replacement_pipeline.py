from __future__ import annotations

import unittest

from specromancy.exit_codes import ExitCode

from tests.features.contract.support import CliRepository


class ReplacementPipelineContractTests(unittest.TestCase):
    def test_unrelated_phase_names_complete_through_the_public_cli(self) -> None:
        repo = CliRepository(replacement=True)
        try:
            run_id = repo.initialize("Uppercase the source value")
            artifacts = {
                "inspect": "# Inspection\n## Observations\nalpha\n## Selected Operation\nuppercase\n",
                "transform": "# Transformation\n## Operation\nuppercase\n## Result\nALPHA\n",
                "verify": "# Verification\n## Checks\nMatched.\n## Decision\nAccepted.\n",
            }
            for phase in ("inspect", "transform"):
                repo.start_and_write(run_id, phase, artifacts[phase])
                result = repo.command("validate", run_id, phase)
                self.assertEqual(result.returncode, ExitCode.AGENT_ACTION_REQUIRED)
            repo.start_and_write(run_id, "verify", artifacts["verify"])
            completed = repo.command(
                "validate", run_id, "verify", "--outcome", "accepted"
            )
            self.assertEqual(completed.returncode, ExitCode.SUCCESS, completed.stderr)
            terminal = repo.payload(completed)["status"]["terminal_result"]
            self.assertEqual(terminal["outcome"], "accepted")
        finally:
            repo.close()


if __name__ == "__main__":
    unittest.main()
