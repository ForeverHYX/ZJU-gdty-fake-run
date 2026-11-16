"""Offline regression check for map tile coverage."""
import importlib.util
import io
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class RouteRenderingTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow is required to render a map")
    def test_map_tiles_cover_aspect_ratio_padding(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "route_img.py"
            shutil.copyfile(ROOT / script.name, script)
            (root / "config.json").write_text(
                '{"user_id":"offline-user","brand":"offline-brand"}', encoding="utf-8"
            )
            (root / "token.txt").write_text("offline-placeholder", encoding="utf-8")
            build_image = runpy.run_path(str(script))["build_image"]

            colour = (40, 100, 180)
            tile = io.BytesIO()
            Image.new("RGB", (256, 256), colour).save(tile, format="PNG")
            output = root / "map.png"
            points = [
                {"longitude": 101.87, "latitude": 201.12},
                {"longitude": 101.95, "latitude": 202.60},
            ]
            with patch.dict(build_image.__globals__, {
                "mercator": lambda lat, lon, zoom: (lon, lat),
                "fetch_tile": lambda x, y, zoom: tile.getvalue(),
            }):
                build_image(points, "0.4", "2", output)

            with Image.open(output) as image:
                self.assertEqual(image.size, (1500, 1120))
                for corner in ((0, 0), (1499, 0), (0, 1119), (1499, 1119)):
                    self.assertEqual(image.getpixel(corner), colour)
