from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "launcher" / "NaverMap.applescript"


class LauncherSourceTests(unittest.TestCase):
    def test_prefers_iterm2_with_terminal_fallback(self):
        source = SCRIPT.read_text()
        self.assertIn('application id "com.googlecode.iterm2"', source)
        self.assertIn('tell application "Terminal"', source)
        self.assertIn('create window with default profile', source)

    def test_closes_matching_iterm_session_by_tty(self):
        source = SCRIPT.read_text()
        self.assertIn('sessions of w', source)
        self.assertIn('(tty of s) is theTTY', source)
