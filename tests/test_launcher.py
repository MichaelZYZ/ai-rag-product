import errno
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from run_server import available_port


class LauncherTests(unittest.TestCase):
    def test_windows_python_probes_execute_without_embedded_double_quotes(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / 'bootstrap_windows.ps1').read_text()
        snippets = re.findall(r'-c "([^"\n]+)" 2>\$null', script)
        self.assertEqual(len(snippets), 2)
        # Check compatibility with legacy native arguments: embedded double
        # quotes cannot survive the Windows command-line parser. The probes
        # deliberately contain none, and must still execute as valid Python.
        for snippet in snippets:
            result = subprocess.run([sys.executable, '-c', snippet], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        detected = subprocess.run([sys.executable, '-c', snippets[0]], cwd=root,
                                  capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(detected.stdout)['version'], sys.version.split()[0])

    def test_uses_next_port_when_default_is_occupied(self):
        attempts = []

        class Probe:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def bind(self, address):
                attempts.append(address[1])
                if address[1] == 8000:
                    raise OSError(errno.EADDRINUSE, 'busy')

        with patch('run_server.socket.socket', return_value=Probe()):
            self.assertEqual(available_port(), 8001)
        self.assertEqual(attempts, [8000, 8001])


if __name__ == '__main__':
    unittest.main()
