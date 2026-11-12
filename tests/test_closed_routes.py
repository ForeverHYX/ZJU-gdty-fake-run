"""Offline regression check for continuous traversal of closed routes."""
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ClosedRouteTests(unittest.TestCase):
    def test_closed_routes_remain_continuous_after_multiple_laps(self):
        for route_id in ("zijingang-east", "zijingang-west"):
            with self.subTest(route=route_id), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for filename in ("forge2.py", "route_catalog.json"):
                    shutil.copyfile(ROOT / filename, root / filename)
                config = {
                    "user_id": "offline-user",
                    "brand": "offline-brand",
                    "device_info": "offline-device",
                    "route_id": route_id,
                }
                (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
                (root / "token.txt").write_text("offline-placeholder", encoding="utf-8")
                forge = runpy.run_path(str(root / "forge2.py"))
                course, _ = forge["make_course"](3300)
                walker = forge["Walker"](course)
                at_arc, distance = forge["at_arc"], forge["hav"]
                lap_length = forge["TOTAL_POLY"]
                self.assertGreater(3300 / lap_length, 8)
                self.assertLess(distance(at_arc(lap_length - 0.5), at_arc(lap_length + 0.5)), 1.01)

                previous = at_arc(course[0])
                travelled = 0.0
                for _ in range(3300):
                    current = at_arc(walker.step(1))
                    travelled += distance(previous, current)
                    previous = current
                self.assertAlmostEqual(travelled, 3300, delta=5)
