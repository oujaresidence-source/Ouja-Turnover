# -*- coding: utf-8 -*-
"""The map tiles and the dots drawn on top MUST share one projection.

If these drift apart, every circle sits a street or two away from its building — and it
still looks plausible, which is the dangerous part. So the dashboard's JS projection is
reimplemented here and asserted equal to the server's tile maths.

Mirror of the JS in DASHBOARD_HTML:
    function _covMercator(lat, lng, z){
      var scale = Math.pow(2, z);
      var s = Math.min(0.9999, Math.max(-0.9999, Math.sin(lat*Math.PI/180)));
      return {x: 256*((lng+180)/360)*scale,
              y: 256*(0.5 - Math.log((1+s)/(1-s))/(4*Math.PI))*scale};
    }
    var x = W/2 + (p.x - ctr.x);   var y = H/2 + (p.y - ctr.y);
"""

import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coverage_study import tiles


def js_mercator(lat, lng, z):
    """Byte-for-byte port of the dashboard's _covMercator."""
    scale = 2 ** z
    s = min(0.9999, max(-0.9999, math.sin(lat * math.pi / 180)))
    return (256 * ((lng + 180) / 360) * scale,
            256 * (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * scale)


RIYADH = (24.7136, 46.6753)
NUZHA = (24.7583056, 46.7096111)


class TestProjectionsAgree(unittest.TestCase):
    def test_server_and_client_projections_are_identical(self):
        for z in (10, 11, 13, 16):
            for lat, lng in (RIYADH, NUZHA, (24.8289, 46.7362), (24.87, 46.60)):
                a = tiles.world_px(lat, lng, z)
                b = js_mercator(lat, lng, z)
                self.assertAlmostEqual(a[0], b[0], places=6, msg="lng z=%d" % z)
                self.assertAlmostEqual(a[1], b[1], places=6, msg="lat z=%d" % z)

    def test_centre_point_lands_in_the_middle_of_the_image(self):
        W, H, z = 700, 440, 12
        ctr = tiles.world_px(NUZHA[0], NUZHA[1], z)
        p = js_mercator(NUZHA[0], NUZHA[1], z)
        self.assertAlmostEqual(W / 2 + (p[0] - ctr[0]), W / 2, places=6)
        self.assertAlmostEqual(H / 2 + (p[1] - ctr[1]), H / 2, places=6)

    def test_a_point_north_is_drawn_above_the_centre(self):
        z, ctr = 12, tiles.world_px(RIYADH[0], RIYADH[1], 12)
        north = js_mercator(RIYADH[0] + 0.05, RIYADH[1], z)
        self.assertLess(north[1] - ctr[1], 0)          # smaller y = higher up

    def test_a_point_east_is_drawn_right_of_the_centre(self):
        z, ctr = 12, tiles.world_px(RIYADH[0], RIYADH[1], 12)
        east = js_mercator(RIYADH[0], RIYADH[1] + 0.05, z)
        self.assertGreater(east[0] - ctr[0], 0)

    def test_one_zoom_step_doubles_the_pixel_separation(self):
        a1 = tiles.world_px(*NUZHA, z=12)
        b1 = tiles.world_px(RIYADH[0], RIYADH[1], 12)
        a2 = tiles.world_px(*NUZHA, z=13)
        b2 = tiles.world_px(RIYADH[0], RIYADH[1], 13)
        d1 = math.hypot(a1[0] - b1[0], a1[1] - b1[1])
        d2 = math.hypot(a2[0] - b2[0], a2[1] - b2[1])
        self.assertAlmostEqual(d2 / d1, 2.0, places=6)


class TestTileGuards(unittest.TestCase):
    def test_absurd_view_is_refused_rather_than_hammering_the_tile_servers(self):
        with self.assertRaises(Exception):
            tiles.render(24.7, 46.7, 19, 4000, 4000)

    def test_identifying_user_agent_is_set(self):
        # OSM policy: a default library User-Agent gets blocked, and should be.
        self.assertIn("Ouja", tiles.UA)
        self.assertIn("http", tiles.UA)

    def test_attribution_string_exists_and_is_rendered_by_the_page(self):
        self.assertIn("OpenStreetMap", tiles.ATTRIBUTION)
        import bot
        self.assertIn("OpenStreetMap", bot.DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
