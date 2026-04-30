import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.geometry_11d import (
    UNIT_11D_BALL_SURFACE,
    UNIT_11D_BALL_VOLUME,
    bereken_11d_bol,
    measure_geometry_11d,
    radius_from_autonomy,
    radius_from_frequency,
)


class TestGeometry11D(unittest.TestCase):
    def test_unit_11d_ball_uses_philip_formula(self):
        expected_volume = 64.0 * (math.pi ** 5) / 10395.0
        expected_surface = 64.0 * (math.pi ** 5) / 945.0
        volume, oppervlakte = bereken_11d_bol(1.0)

        self.assertAlmostEqual(UNIT_11D_BALL_VOLUME, expected_volume)
        self.assertAlmostEqual(UNIT_11D_BALL_SURFACE, expected_surface)
        self.assertAlmostEqual(volume, expected_volume)
        self.assertAlmostEqual(oppervlakte, expected_surface)

    def test_radius_scales_to_power_11(self):
        volume, oppervlakte = bereken_11d_bol(2.0)
        self.assertAlmostEqual(
            volume,
            UNIT_11D_BALL_VOLUME * (2.0 ** 11),
        )
        self.assertAlmostEqual(
            oppervlakte,
            UNIT_11D_BALL_SURFACE * (2.0 ** 10),
        )

    def test_measure_geometry_accepts_11d_position(self):
        measured = measure_geometry_11d([0.0] * 11)
        self.assertEqual(measured["dimension_count"], 11)
        self.assertEqual(measured["radius"], 1.0)
        self.assertGreater(measured["volume"], 0)
        self.assertGreater(measured["oppervlakte"], 0)

    def test_invalid_radius_raises(self):
        with self.assertRaises(ValueError):
            bereken_11d_bol(-0.1)
        with self.assertRaises(ValueError):
            bereken_11d_bol(float("nan"))

    def test_radius_from_frequency_maps_dreamcycle_band(self):
        self.assertEqual(radius_from_frequency(418.0), 1.0)
        self.assertEqual(radius_from_frequency(432.0), 11.0)
        self.assertEqual(radius_from_frequency(425.0), 6.0)
        self.assertEqual(radius_from_frequency(500.0), 11.0)

    def test_radius_from_autonomy_maps_and_clamps(self):
        self.assertEqual(radius_from_autonomy(0.0), 1.0)
        self.assertEqual(radius_from_autonomy(0.5), 6.0)
        self.assertEqual(radius_from_autonomy(1.0), 11.0)
        self.assertEqual(radius_from_autonomy(-1.0), 1.0)
        self.assertEqual(radius_from_autonomy(2.0), 11.0)


if __name__ == "__main__":
    unittest.main()
