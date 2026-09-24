import os
import subprocess
import sys
import unittest

from specromancy.locking import _pid_is_alive


class PidLivenessTests(unittest.TestCase):
    def test_current_process_is_alive(self) -> None:
        self.assertTrue(_pid_is_alive(os.getpid()))

    def test_completed_process_is_not_alive(self) -> None:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait(timeout=10)

        self.assertFalse(_pid_is_alive(process.pid))

    def test_nonpositive_pid_is_not_alive(self) -> None:
        self.assertFalse(_pid_is_alive(0))
        self.assertFalse(_pid_is_alive(-1))


if __name__ == "__main__":
    unittest.main()
