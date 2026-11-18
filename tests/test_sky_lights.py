"""Halo 2 sky lighting becomes Halo 3 sky lights shaped like Bungie's: one sun and sky patches, 200 in all."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import sky_lights

# Coagulation's sky, as the extractor reads it from the map.
COAGULATION = dict(outdoor_ambient=[0.788235, 0.835294, 0.870588], lights=[dict(
    direction=[0.8795877, 0.0769540, 0.4694716], color=[0.94902, 0.909804, 0.87451], power=0.3, diameter=0.0034906585, flags=15)])


class SkyLights(unittest.TestCase):
    def test_coagulation(self):
        lights = sky_lights.h2_sky_lights(COAGULATION)
        self.assertEqual(len(lights), 200)
        sun, patches = lights[-1], lights[:-1]
        self.assertAlmostEqual(sun['solid_angle'], sky_lights.MIN_SUN_ANGLE)
        self.assertAlmostEqual(math.degrees(math.asin(sun['direction'][2])), 28, places=0)
        # Sun light on a surface facing it (7.5 x its color), and sky light on flat ground.
        for got, color in zip(sun['intensity'], COAGULATION['lights'][0]['color']):
            self.assertAlmostEqual(got * sun['solid_angle'], sky_lights.SUN_LIGHT_PER_POWER * .3 * color, places=3)
        # Low sun: on flat ground it gives about Bungie's sun light (3.4 - 5.8 on their high suns' ground).
        self.assertTrue(3.0 < sun['intensity'][0] * sun['solid_angle'] * sun['direction'][2] < 5.8)
        flat = [sum(p['intensity'][c] * p['solid_angle'] * p['direction'][2] for p in patches) for c in range(3)]
        for got, ambient in zip(flat, COAGULATION['outdoor_ambient']):
            self.assertAlmostEqual(got, sky_lights.SKY_LIGHT * ambient, places=4)
        self.assertTrue(all(p['direction'][2] > 0 and abs(math.hypot(*p['direction']) - 1) < 1e-9 for p in patches))
        self.assertAlmostEqual(patches[0]['solid_angle'], 0.06314758, places=7)
        self.assertGreater(sun['intensity'][0], sun['intensity'][2], 'warm sun color kept')

    def test_strengths(self):
        base = sky_lights.h2_sky_lights(COAGULATION)
        brighter = sky_lights.h2_sky_lights(COAGULATION, sun=.5, sky=2)
        self.assertAlmostEqual(brighter[-1]['intensity'][0], base[-1]['intensity'][0] * .5)
        self.assertAlmostEqual(brighter[0]['intensity'][2], base[0]['intensity'][2] * 2)
        no_sun = sky_lights.h2_sky_lights(COAGULATION, sun=0)
        self.assertEqual(len(no_sun), 200)
        self.assertTrue(all(l['solid_angle'] == sky_lights.PATCH_ANGLE for l in no_sun))

    def test_sun_without_ambient(self):
        # Beaver Creek: a sun and no outdoor ambient. A sun-only sky made Tool assert, so the shade
        # gets a dim fill tinted like the sun; the sun stays last.
        lights = sky_lights.h2_sky_lights(dict(COAGULATION, outdoor_ambient=[0, 0, 0]))
        self.assertEqual(len(lights), 200)
        self.assertAlmostEqual(lights[-1]['solid_angle'], sky_lights.MIN_SUN_ANGLE)
        flat = [sum(p['intensity'][c] * p['solid_angle'] * p['direction'][2] for p in lights[:-1]) for c in range(3)]
        self.assertAlmostEqual(sum(flat) / 3, sky_lights.SKY_LIGHT * sky_lights.FALLBACK_AMBIENT, places=4)
        self.assertGreater(flat[0], flat[2], 'tinted like the warm sun')

    def test_nothing_to_light(self):
        self.assertEqual(sky_lights.h2_sky_lights(None), [])
        self.assertEqual(sky_lights.h2_sky_lights(dict(outdoor_ambient=[0, 0, 0], lights=[])), [])
        # A light that only lit indirectly (no direct flag) is not a sun; the sky still lights.
        only_indirect = dict(COAGULATION, lights=[dict(COAGULATION['lights'][0], flags=8)])
        lights = sky_lights.h2_sky_lights(only_indirect)
        self.assertEqual(len(lights), 200)
        self.assertTrue(all(l['solid_angle'] == sky_lights.PATCH_ANGLE for l in lights))


if __name__ == '__main__':
    unittest.main()
