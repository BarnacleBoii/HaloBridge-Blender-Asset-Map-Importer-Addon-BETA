"""Write the level file (ASS) with the Halo toolset in background Blender processes.

The toolset's exporter is slow on big levels and blocks Blender while it runs. Its ASS
output is regular: a MATERIALS list, one OBJECTS block per distinct mesh (geometry in
the mesh's own space, independent of where it is placed), and one INSTANCES block per
placement. So:

* plan() (Blender's main thread, quick) hashes every mesh, and writes small .blend files:
  the meshes without a saved piece, split into a few batches, and a stand-in scene where
  every mesh is one triangle (its placements are what matter).
* run() (any thread) exports those files with the toolset in parallel background Blender
  processes, saves each mesh's OBJECTS block as a piece, and merges pieces, materials and
  the stand-in scene's placements into the final ASS.

A mesh that hasn't changed is never exported again. The toolset still writes every
geometry block and every placement; HaloBridge only reorders and renumbers them.
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION = 1
EXPORT_ARGS = dict(game_title='halo3', scale_enum='1', hidden_geo=False, nonrender_geo=False, apply_modifiers=True,
                   triangulate_faces=True, edge_split=False, clean_normalize_weights=False)
NL = b'\r\n'


def worker_count():
    return max(1, min(4, (os.cpu_count() or 2) // 2))


# ---------------------------------------------------------------- planning (main thread)

def _settings_signature(props):
    values = []
    for prop in props.bl_rna.properties:
        if prop.identifier == 'rna_type' or prop.type in ('POINTER', 'COLLECTION'):
            continue
        value = getattr(props, prop.identifier)
        if not isinstance(value, (str, int, float, bool)):
            value = tuple(value)
        values.append((prop.identifier, repr(value)))
    return tuple(values)


def mesh_signature(mesh, scale, context):
    """Everything the toolset reads to write this mesh's OBJECTS block."""
    import numpy as np
    from . import compat
    h = hashlib.sha1(repr((VERSION, context, tuple(round(s, 5) for s in scale))).encode())
    def add(collection, attribute, count, dtype):
        values = np.empty(count, dtype=dtype)
        if count:
            collection.foreach_get(attribute, values)
        h.update(values.tobytes())
    add(mesh.vertices, 'co', len(mesh.vertices) * 3, np.float32)
    add(mesh.loops, 'vertex_index', len(mesh.loops), np.int32)
    add(mesh.polygons, 'loop_start', len(mesh.polygons), np.int32)
    add(mesh.polygons, 'loop_total', len(mesh.polygons), np.int32)
    add(mesh.polygons, 'material_index', len(mesh.polygons), np.int32)
    h.update(np.asarray(compat.corner_normals(mesh), dtype=np.float32).tobytes())
    for layer in mesh.uv_layers:
        h.update(layer.name.encode())
        add(layer.data, 'uv', len(layer.data) * 2, np.float32)
    for attribute in getattr(mesh, 'color_attributes', []):
        h.update((attribute.name + attribute.domain + attribute.data_type).encode())
        add(attribute.data, 'color', len(attribute.data) * 4, np.float32)
    for mat in mesh.materials:
        # The ASS names a material by its override (the Halo shader); export copies of the
        # same material get new Blender names (.001, .002 ...) every preparation.
        h.update(repr((mat.ass_jms.name_override or mat.name, _settings_signature(mat.ass_jms)) if mat else None).encode())
    return h.hexdigest()


def plan(scene, path, chunks, workers=None):
    """Prepare the background export of scene's meshes to path. Returns a plain-data job."""
    steps = plan_steps(scene, path, chunks, workers)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def plan_steps(scene, path, chunks, workers=None):
    """plan(), yielding between meshes and files so Blender keeps responding."""
    import bpy
    from . import compat
    path = Path(path); chunks = Path(chunks); chunks.mkdir(parents=True, exist_ok=True)
    work = path.parent / (path.stem + '_parts'); work.mkdir(parents=True, exist_ok=True)
    module = compat.toolset_module()
    context = (scene.unit_settings.system, round(scene.unit_settings.scale_length, 6), json.dumps(EXPORT_ARGS, sort_keys=True),
               '.'.join(map(str, getattr(module, 'bl_info', {}).get('version', ()))), bpy.app.version_string)
    objects = [o for o in scene.objects]
    if any(o.type != 'MESH' or o.parent or o.hide_render or o.hide_viewport for o in objects):
        raise ValueError('only visible, unparented mesh objects can be exported in parts')
    signatures = {}; order = []; instances = []
    for obj in objects:
        key = (obj.data.as_pointer(), tuple(round(s, 5) for s in obj.matrix_world.to_scale()))
        if key not in signatures:
            yield
            signatures[key] = mesh_signature(obj.data, key[1], context)
        sig = signatures[key]
        name = obj.ass_jms.name_override or obj.name
        instances.append((name, sig))
        if sig not in order:
            order.append(sig)
    sources = {}
    for obj in objects:
        key = (obj.data.as_pointer(), tuple(round(s, 5) for s in obj.matrix_world.to_scale()))
        sources.setdefault(signatures[key], (obj.data, key[1]))
    missing = [sig for sig in order if not (chunks / (sig + '.piece')).is_file()]
    workers = workers or worker_count()
    batches = [[] for _ in range(min(workers, len(missing)))]
    weights = [0] * len(batches)
    for sig in sorted(missing, key=lambda s: -len(sources[s][0].loops)):
        i = weights.index(min(weights)); batches[i].append(sig); weights[i] += len(sources[sig][0].loops) + 1

    def write(name, fill):
        # Only a collection of objects is saved: writing a Scene this way crashes Blender 5.2.
        # The background Blender links the collection into its own empty scene.
        temp = bpy.data.collections.new('hb_' + name)
        made_objects, made_meshes = [], []
        try:
            names = fill(temp, made_objects, made_meshes)
            blend = work / (name + '.blend')
            bpy.data.libraries.write(str(blend), {temp}, path_remap='NONE', compress=False)
            return dict(blend=str(blend), out=str(work / (name + '.ASS')), names=names, collection=temp.name)
        finally:
            bpy.data.batch_remove([*made_objects, temp, *made_meshes])

    jobs = []
    for index, batch in enumerate(batches):
        yield
        def fill(temp, made_objects, made_meshes, batch=batch):
            names = {}
            for n, sig in enumerate(batch):
                mesh, scale = sources[sig]
                o = bpy.data.objects.new('hb_part_%d' % n, mesh); temp.objects.link(o); made_objects.append(o)
                o.scale = scale; names[o.name] = sig
            return names
        jobs.append(write('meshes_%d' % index, fill))

    def stand_in(temp, made_objects, made_meshes):
        # One triangle per mesh: the toolset writes the real placements quickly.
        proxies = {}
        for obj in objects:
            mesh = obj.data
            if mesh.as_pointer() not in proxies:
                proxy = bpy.data.meshes.new('hb_stand_in'); made_meshes.append(proxy)
                proxy.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)]); proxy.uv_layers.new()
                if mesh.materials: proxy.materials.append(mesh.materials[0])
                proxies[mesh.as_pointer()] = proxy
            o = bpy.data.objects.new('hb_stand_in', proxies[mesh.as_pointer()]); temp.objects.link(o); made_objects.append(o)
            o.matrix_world = obj.matrix_world.copy()
            o.ass_jms.name_override = obj.ass_jms.name_override or obj.name
        return {}
    yield
    placements = write('placements', stand_in)
    return dict(version=VERSION, path=str(path), chunks=str(chunks), work=str(work), order=order, instances=instances,
                batches=jobs, placements=placements, blender=bpy.app.binary_path,
                units=[scene.unit_settings.system, scene.unit_settings.scale_length], addon=compat.toolset_addon_name(),
                worker=str(Path(__file__).with_name('ass_worker.py')), reused=len(order) - len(missing), exported=len(missing))


# ---------------------------------------------------------------- parsing and merging (any thread)

def sections(data):
    """{name: (count, [block bodies])} plus the header text, from an ASS file's bytes."""
    pieces = data.split(NL + b';### ')
    result = {'HEADER': pieces[0]}
    for piece in pieces[1:]:
        name, rest = piece.split(b' ###' + NL, 1)
        count, rest = rest.split(NL, 1) if NL in rest else (rest, b'')
        tag = {b'MATERIALS': b'MATERIAL', b'OBJECTS': b'OBJECT', b'INSTANCES': b'INSTANCE'}.get(name, name)
        bodies = []
        for block in (NL + rest).split(NL + b';' + tag + b' ')[1:]:
            body = block.split(NL, 1)[1] if NL in block else b''
            bodies.append(body[:-2] if body.endswith(NL) else body)
        result[name.decode()] = (int(count), bodies)
    return result


def _triangles_start(body):
    first = body.find(b'\t\t')
    if first < 0:
        return -1
    return body.rfind(NL, 0, body.rfind(NL, 0, first)) + 2  # the triangle-count line


def remap_materials(body, mapping):
    start = _triangles_start(body)
    if start < 0:
        return body
    head, tail = body[:start], body[start:]
    count, lines = tail.split(NL, 1) if NL in tail else (tail, b'')
    out = []
    for line in lines.split(NL):
        tab = line.find(b'\t')
        out.append(str(mapping[int(line[:tab])]).encode() + line[tab:] if tab > 0 else line)
    return head + count + NL + NL.join(out)


def used_materials(body):
    start = _triangles_start(body)
    if start < 0:
        return []
    lines = body[start:].split(NL)[1:]
    return sorted({int(line[:line.find(b'\t')]) for line in lines if line.find(b'\t') > 0})


def save_piece(chunks, sig, materials, body):
    used = used_materials(body)
    local = {old: new for new, old in enumerate(used)}
    header = json.dumps({'version': VERSION, 'materials': [materials[i].decode('latin-1') for i in used]}).encode()
    temp = Path(chunks) / (sig + '.piece.tmp')
    temp.write_bytes(header + b'\n' + remap_materials(body, local))
    os.replace(temp, Path(chunks) / (sig + '.piece'))


def load_piece(chunks, sig):
    data = (Path(chunks) / (sig + '.piece')).read_bytes()
    header, body = data.split(b'\n', 1)
    return [m.encode('latin-1') for m in json.loads(header)['materials']], body


def _export(job, task, cancel, log):
    from .jobs import run_process
    args = json.dumps(dict(out=task['out'], addon=job['addon'], options=EXPORT_ARGS, blend=task['blend'],
                           collection=task['collection'], units=job['units']))
    run_process([job['blender'], '-b', '--factory-startup', '--python-exit-code', '1',
                 '--python', job['worker'], '--', args], log, cancel=cancel)
    if not Path(task['out']).is_file():
        raise RuntimeError('The Halo toolset did not write ' + task['out'] + '; see ' + str(log))


def run(job, cancel=None, progress=None):
    """Export the planned parts in parallel, save new pieces and write the merged ASS."""
    progress = progress or (lambda message: None)
    work = Path(job['work']); chunks = Path(job['chunks'])
    tasks = job['batches'] + [job['placements']]
    progress(f'Writing the level file in background Blender processes: {job["exported"]:,} mesh(es) to export, '
             f'{job["reused"]:,} unchanged and reused')
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = [pool.submit(_export, job, task, cancel, work / (Path(task['out']).stem + '.log')) for task in tasks]
        for future in futures:
            future.result()
    for task in job['batches']:
        parsed = sections(Path(task['out']).read_bytes())
        materials = parsed['MATERIALS'][1]; bodies = parsed['OBJECTS'][1]
        for instance in parsed['INSTANCES'][1]:
            lines = instance.split(NL)
            name = lines[1].strip(b'"').decode('utf-8')
            if name in task['names']:
                save_piece(chunks, task['names'][name], materials, bodies[int(lines[0])])
    placements = sections(Path(job['placements']['out']).read_bytes())
    names = dict(job['instances'])
    index = {sig: i for i, sig in enumerate(job['order'])}
    material_index = {}; material_list = []; object_bodies = []
    for sig in job['order']:
        materials, body = load_piece(chunks, sig)
        mapping = {}
        for local, block in enumerate(materials):
            if block not in material_index:
                material_index[block] = len(material_list); material_list.append(block)
            mapping[local] = material_index[block]
        object_bodies.append(remap_materials(body, mapping))
    instance_bodies = []
    for body in placements['INSTANCES'][1]:
        lines = body.split(NL)
        if lines[0] != b'-1':
            name = lines[1].strip(b'"').decode('utf-8')
            lines[0] = str(index[names[name]]).encode()
        instance_bodies.append(NL.join(lines))
    if len(instance_bodies) != len(job['instances']) + 1:
        raise RuntimeError('The level file parts do not match the scene (%d placements for %d objects).' % (len(instance_bodies) - 1, len(job['instances'])))
    temp = Path(job['path'] + '.writing')
    with temp.open('wb') as stream:
        stream.write(placements['HEADER'])
        for name, tag, bodies in (('MATERIALS', b'MATERIAL', material_list), ('OBJECTS', b'OBJECT', object_bodies),
                                  ('INSTANCES', b'INSTANCE', instance_bodies)):
            stream.write(NL + b';### ' + name.encode() + b' ###' + NL + str(len(bodies)).encode() + NL)
            for i, body in enumerate(bodies):
                stream.write(NL + b';' + tag + b' ' + str(i).encode() + NL + body + NL)
    os.replace(temp, job['path'])
    # Keep only the pieces this level uses, so the folder doesn't grow without limit.
    keep = {sig + '.piece' for sig in job['order']}
    for piece in chunks.glob('*.piece'):
        if piece.name not in keep:
            piece.unlink(missing_ok=True)
    import shutil
    shutil.rmtree(work, ignore_errors=True)
    return job['path']
