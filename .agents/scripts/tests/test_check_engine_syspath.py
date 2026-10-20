"""The sys.path checker must flag the shapes that actually broke production,
and must stay quiet on the correct ones. Each bad case below is a shape grep
cannot see (multi-line, through a variable, through `.parents[n]`)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_engine_syspath import check_source  # noqa: E402

BAD = {
    "direct": 'import sys\nfrom pathlib import Path\n'
              'sys.path.insert(0, str(Path(__file__).parent / "au_racing_engine"))\n',
    "via variable (the reflector shape)":
        'import sys\nfrom pathlib import Path\n'
        '_ENGINE = Path(__file__).resolve().parents[2] / "hkjc_wong_choi_auto"'
        ' / "scripts" / "hkjc_racing_engine"\n'
        'sys.path.insert(0, str(_ENGINE))\n',
    "multi-line":
        'import sys\nfrom pathlib import Path\n_E = (\n    Path(__file__).parent\n'
        '    / "scripts"\n    / "au_racing_engine"\n)\nsys.path.append(str(_E))\n',
    "os.path.join": 'import os, sys\n'
                    'sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hkjc_racing_engine"))\n',
}
GOOD = {
    "parent of the package":
        'import sys\nfrom pathlib import Path\n'
        '_ENGINE = Path(__file__).resolve().parents[2] / "hkjc_wong_choi_auto" / "scripts" / "hkjc_racing_engine"\n'
        'sys.path.insert(0, str(_ENGINE.parent))\n',
    "scripts dir": 'import sys\nfrom pathlib import Path\n'
                   'sys.path.insert(0, str(Path(__file__).parent / "scripts"))\n',
    "unrelated": 'import sys\nsys.path.insert(0, "/opt/lib")\n',
}


class CheckEngineSysPath(unittest.TestCase):
    def test_flags_every_historical_shape(self):
        for name, src in BAD.items():
            with self.subTest(name):
                self.assertTrue(check_source(src, name), f"missed: {name}")

    def test_quiet_on_correct_shapes(self):
        for name, src in GOOD.items():
            with self.subTest(name):
                self.assertEqual(check_source(src, name), [])

    def test_live_repo_is_clean(self):
        from check_engine_syspath import main
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
