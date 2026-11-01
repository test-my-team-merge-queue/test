"""Two independent changes can violate a shared capacity constraint."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CompatibilityTest(unittest.TestCase):
    def test_capacity(self):
        values = [
            int((ROOT / "config" / name).read_text().strip())
            for name in ("feature_a.txt", "feature_b.txt")
        ]
        for value in values:
            self.assertIn(value, (0, 1), "Each feature must be 0 or 1")
        self.assertLessEqual(
            sum(values), 1,
            "Combined capacity exceeded: feature A and B cannot both be enabled",
        )


if __name__ == "__main__":
    unittest.main()
