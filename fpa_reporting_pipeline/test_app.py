"""Runs the Streamlit app headless and checks it renders without errors."""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class App(unittest.TestCase):

    def test_renders_every_month(self):
        at = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=120).run()
        self.assertFalse(at.exception)
        for month in ("2026-01", "2026-08"):
            at.sidebar.selectbox[0].set_value(month).run()
            self.assertFalse(at.exception, month)
            self.assertEqual(len(at.metric), 3)


if __name__ == "__main__":
    unittest.main()
