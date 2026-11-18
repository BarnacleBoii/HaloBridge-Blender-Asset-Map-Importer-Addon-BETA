"""Halo 2 sky layers keep their draw order in Halo 3: a covering back layer is opaque, the rest sort in thirds."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge.sky_export import layer_order, PRE_PASS, NORMAL, POST_PASS

# Coagulation: blue sky dome (covers everything), moons, sun glow, heavenly glow, ring, fog band, clouds.
names = ['stars', 'moon2', 'moon', 'sun', 'glow', 'ring', 'fog', 'clouds']
converted = {n: dict(blend='additive' if n == 'sun' else 'alpha', covers=n == 'stars') for n in names}
result = layer_order(converted, {n: i for i, n in enumerate(names)})
assert result['stars'] == dict(blend='opaque', additive=False), result['stars']
assert [result[n]['sort_layer'] for n in names[1:]] == [PRE_PASS] * 3 + [NORMAL] * 2 + [POST_PASS] * 2, result
assert result['ring']['sort_layer'] > result['moon']['sort_layer'] and result['clouds']['sort_layer'] > result['ring']['sort_layer']

# A back layer with see-through parts stays see-through, first in order.
converted['stars']['covers'] = False
result = layer_order(converted, {n: i for i, n in enumerate(names)})
assert result['stars'] == dict(sort_layer=PRE_PASS), result['stars']

# Order is by draw position, not by the material list; non-Halo 2 materials (no blend) are left alone.
converted['other'] = dict(name='x')
result = layer_order(converted, {'ring': 0, 'stars': 1, 'other': 2})
assert result['ring'] == dict(sort_layer=PRE_PASS) and result['stars'] == dict(sort_layer=NORMAL) and 'other' not in result, result
assert layer_order(converted, {}) == {}
print('PASS: Halo 2 sky layers keep their draw order in Halo 3')
