"""The quick test compile's level file: only dense objects, once each, plus the sky boundary."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quick_test', ROOT / 'halo_bridge' / 'quick_test.py')
qt = importlib.util.module_from_spec(spec); spec.loader.exec_module(qt)
spec = importlib.util.spec_from_file_location('ass_parts', ROOT / 'halo_bridge' / 'ass_parts.py')
ass_parts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ass_parts)
NL = '\r\n'


def material(name, flags):
    return f'"{name}"{NL}""{NL}2{NL}"BM_FLAGS {flags}"{NL}"BM_LMRES 1"'


def mesh(triangles, mat):
    lines = ['"MESH"', '""', '""', str(triangles * 3)]
    for i in range(triangles * 3):
        lines += [f'{i}\t0\t0', '0\t0\t1', '0\t0\t0', '0', '1', '0\t0\t0', '']
    lines.append(str(triangles))
    lines += [f'{mat}\t\t{3 * t}\t{3 * t + 1}\t{3 * t + 2}' for t in range(triangles)]
    return NL.join(lines)


def instance(index, name, unique):
    return NL.join([str(index), f'"{name}"', str(unique), '0', '0', '0\t0\t0\t1', '5\t6\t7', '1', '0\t0\t0\t1', '0\t0\t0', '1'])


def ass(materials, objects, instances):
    out = [f';### HEADER ###{NL}7{NL}"BLENDER"{NL}"5.2"{NL}"user"{NL}"PC"{NL}']
    for name, tag, blocks in (('MATERIALS', 'MATERIAL', materials), ('OBJECTS', 'OBJECT', objects), ('INSTANCES', 'INSTANCE', instances)):
        out.append(f'{NL};### {name} ###{NL}{len(blocks)}{NL}')
        out += [f'{NL};{tag} {i}{NL}{body}{NL}' for i, body in enumerate(blocks)]
    return ''.join(out).encode()


class QuickTest(unittest.TestCase):
    def test_dense_objects_only(self):
        materials = [material('ground', '0000000000000100000000'), material('leaves', '1001000000000100000000')]
        objects = [mesh(10, 0), mesh(3000, 1), mesh(12, 0)]
        instances = [instance(-1, 'Scene Root', -1), instance(0, '%hb_0.001', 10), instance(1, '%hb_1.001', 11),
                     instance(1, '%hb_2.001', 12), instance(2, 'Sky boundary.001', 13)]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'level.ASS'; source.write_bytes(ass(materials, objects, instances))
            selection = qt.choose(source)
            # The two-sided leaves: 6,000 render triangles but 18,000 render corners.
            self.assertEqual(selection['chosen'], [1]); self.assertEqual(selection['sky'], 2)
            out = qt.write(selection, Path(tmp) / 'test' / 'quick.ASS')
            parsed = ass_parts.sections(out.read_bytes())
            self.assertEqual(parsed['MATERIALS'][0], 2)
            self.assertEqual(parsed['OBJECTS'][0], 2)
            self.assertTrue(parsed['OBJECTS'][1][0].endswith(b'1\t\t8997\t8998\t8999'))
            # Every placement: Tool builds an object placed more than once a second time.
            names = [b.split(b'\r\n')[1] for b in parsed['INSTANCES'][1]]
            self.assertEqual(names, [b'"Scene Root"', b'"%hb_1.001"', b'"%hb_2.001"', b'"Sky boundary.001"'])
            self.assertEqual([b.split(b'\r\n')[0] for b in parsed['INSTANCES'][1]], [b'-1', b'0', b'0', b'1'])

    def test_repeated_objects_with_render_and_collision(self):
        # Small, but placed twice with separate render and collision: Tool's 'merged' pass
        # crashed on one of these in Halo 2: Anniversary Coagulation.
        materials = [material('rock', '0001000000000100000000'), material('rock_collision', '0100100000000100000000'),
                     material('ground', '0000000000000100000000')]
        def mixed(render, collision):
            body = mesh(render + collision, 0).split(NL)
            return NL.join(body[:-(render + collision)] + [l.replace('0\t\t', '1\t\t', 1) if i >= render else l
                                                           for i, l in enumerate(body[-(render + collision):])])
        objects = [mixed(20, 30), mixed(20, 30), mesh(40, 2), mesh(12, 2)]
        instances = [instance(-1, 'Scene Root', -1), instance(0, '%hb_0.001', 1), instance(0, '%hb_3.001', 2),
                     instance(1, '%hb_1.001', 3), instance(2, '%hb_2.001', 4), instance(2, '%hb_4.001', 5),
                     instance(3, 'Sky boundary', 6)]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'level.ASS'; source.write_bytes(ass(materials, objects, instances))
            selection = qt.choose(source)
            # Placed once (1): not tested. The separate collision (0) comes before more collision (2).
            self.assertEqual(selection['chosen'], [0, 2]); self.assertEqual(selection['triangles'], 50 + 80)
            self.assertEqual(len(selection['instances'][0]), 2)
            limit = qt.MAX_MERGED_TRIANGLES; qt.MAX_MERGED_TRIANGLES = 60
            try:self.assertEqual(qt.choose(source)['chosen'], [0])
            finally:qt.MAX_MERGED_TRIANGLES = limit

    def test_nothing_dense(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'level.ASS'
            source.write_bytes(ass([material('ground', '0' * 22)], [mesh(10, 0), mesh(12, 0)],
                                   [instance(-1, 'Scene Root', -1), instance(0, '%hb_0', 1), instance(1, 'Sky boundary', 2)]))
            self.assertEqual(qt.choose(source)['chosen'], [])


if __name__ == '__main__':
    unittest.main()
