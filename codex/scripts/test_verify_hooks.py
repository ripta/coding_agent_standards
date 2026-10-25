import contextlib
import io
import json
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


class VerifyHooksTests(unittest.TestCase):
    def test_trusted_success_emits_valid_json(self):
        verifier = runpy.run_path(str(Path(__file__).with_name("verify_hooks.py")))
        hooks = [{"enabled": True, "trustStatus": "trusted"}]
        output = io.StringIO()
        with patch.dict(verifier["main"].__globals__, discover=lambda cwd: hooks):
            with patch("sys.argv", ["verify_hooks.py", "--json"]), contextlib.redirect_stdout(output):
                self.assertEqual(verifier["main"](), 0)
        self.assertEqual(json.loads(output.getvalue()), hooks)


if __name__ == "__main__":
    unittest.main()
