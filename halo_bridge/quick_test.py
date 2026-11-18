"""Quick test compile: a small level file holding only the level's riskiest objects.

Tool's structure import compiles the whole level in one go and keeps nothing when it
fails, and it only checks an object's limits (render vertices, collision size, broken
collision edges) while building that object, often near the end. Compiling the densest
objects on their own first finds those rejections in a fraction of the time.

The level file is read through a memory map: only the chosen objects are copied.
"""
import mmap
from pathlib import Path

NL = b'\r\n'
# Objects worth testing: near Tool's per-part limits, or with a lot of collision.
RENDER_CORNERS = 15000      # ASS vertices (one per face corner), doubled when two-sided
RENDER_TRIANGLES = 8000     # render triangles, doubled when two-sided
COLLISION_TRIANGLES = 4000
# The objects closest to a limit come first. Tool took 10.7 minutes for 1.5 million
# triangles of Halo 2: Anniversary Coagulation (25 for the full level), so the test is capped.
MAX_TEST_TRIANGLES = 250000
# Tool builds an object placed more than once a second time ('merged'), and it can crash
# there on render and collision it accepted on their own; those objects are tested too,
# with every placement, most collision first.
MAX_MERGED_TRIANGLES = 150000


def _flags(block):
    """BM_FLAGS digits of a MATERIAL block: two-sided, transparent 1/2-sided, render only, collision only."""
    start = block.find(b'"BM_FLAGS ')
    if start < 0:
        return '0' * 8
    return block[start + 10:block.find(b'"', start + 10)].decode('ascii', 'replace')


def _blocks(m, start, end, tag):
    """[(body start, body end)] of each ';TAG i' block between start and end."""
    marker = NL + b';' + tag + b' '
    spans = []
    pos = m.find(marker, start, end)
    while pos >= 0:
        body = m.find(NL, pos + len(marker), end) + 2
        nxt = m.find(marker, body, end)
        stop = nxt if nxt >= 0 else end
        spans.append((body, stop))
        pos = nxt
    return spans


def _trim(m, span):
    body = m[span[0]:span[1]]
    while body.endswith(NL):
        body = body[:-2]
    return body


def _triangles(m, span, materials):
    """(render triangles counting both sides, render corners counting both sides, collision triangles,
    collision-only triangles)."""
    first = m.find(b'\t\t', span[0], span[1])
    if first < 0:
        return 0, 0, 0, 0
    count_line = m.rfind(NL, span[0], m.rfind(NL, span[0], first)) + 2
    lines = m[count_line:span[1]].split(NL)[1:]
    render = collision = separate = 0
    per = {}
    for line in lines:
        tab = line.find(b'\t')
        if tab > 0:
            index = int(line[:tab]); per[index] = per.get(index, 0) + 1
    for index, count in per.items():
        flags = materials[index] if index < len(materials) else '0' * 8
        double = 2 if flags[0] == '1' or flags[2] == '1' else 1
        if flags[4] != '1':
            render += count * double
        else:
            separate += count
        if flags[3] != '1':
            collision += count
    return render, render * 3, collision, separate


def choose(path):
    """Read the level file; return (header, material blocks, risky objects, sky object, instance info)."""
    with open(path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        mat_at = m.find(b';### MATERIALS ###'); obj_at = m.find(b';### OBJECTS ###', mat_at)
        inst_at = m.find(b';### INSTANCES ###', obj_at)
        header = m[:mat_at]
        material_spans = _blocks(m, mat_at, obj_at, b'MATERIAL')
        material_blocks = [_trim(m, s) for s in material_spans]
        flags = [_flags(b) for b in material_blocks]
        object_spans = _blocks(m, obj_at, inst_at, b'OBJECT')
        instance_blocks = [_trim(m, s) for s in _blocks(m, inst_at, len(m), b'INSTANCE')]
        placements = {}; sky = None
        for block in instance_blocks:
            lines = block.split(NL)
            index, name = int(lines[0]), lines[1].strip(b'"').decode('utf-8', 'replace')
            if index < 0:
                continue
            if name.startswith('Sky boundary'):
                sky = index; placements[index] = [block]
            elif name.startswith('%'):
                placements.setdefault(index, []).append(block)
        risky = []; merged = []
        for index, span in enumerate(object_spans):
            if index not in placements or index == sky:
                continue
            # The ASS vertex count is on the 4th body line; small objects need no closer look.
            head = m[span[0]:span[0] + 200].split(NL)
            vertices = int(head[3]) if len(head) > 3 and head[3].isdigit() else 0
            repeated = len(placements[index]) > 1
            if vertices < min(RENDER_CORNERS, COLLISION_TRIANGLES * 3) // 2 and not repeated:
                continue
            render, corners, collision, separate = _triangles(m, span, flags)
            if corners > RENDER_CORNERS or render > RENDER_TRIANGLES or collision > COLLISION_TRIANGLES:
                risky.append((max(corners / 30000, render / 16000, collision / 10000), index, render + collision))
            if repeated and render and collision:
                # A separate collision mesh first (the crash seen), then the most collision.
                merged.append((separate > 0, collision, index, render + collision))
        risky.sort(reverse=True); merged.sort(reverse=True)
        chosen = []; total = 0
        for _, index, triangles in risky:
            if total + triangles > MAX_TEST_TRIANGLES:
                continue
            chosen.append(index); total += triangles
        extra = 0
        for _, _, index, triangles in merged:
            if index in chosen or extra + triangles > MAX_MERGED_TRIANGLES:
                continue
            chosen.append(index); extra += triangles
        total += extra
        chosen.sort()
        bodies = {index: _trim(m, object_spans[index]) for index in chosen + ([sky] if sky is not None else [])}
    return dict(header=header, materials=material_blocks, chosen=chosen, sky=sky, bodies=bodies,
                instances=placements, root=instance_blocks[0], triangles=total, candidates=len(risky))


def write(selection, path):
    """Write the quick-test level file: every material, the chosen objects with all their placements, and the sky boundary."""
    order = list(selection['chosen']) + ([selection['sky']] if selection['sky'] is not None else [])
    renumber = {old: new for new, old in enumerate(order)}
    instances = [selection['root']]
    for old in order:
        # The sky boundary encloses the whole level, so every chosen object stays inside it.
        for block in selection['instances'][old]:
            lines = block.split(NL)
            lines[0] = str(renumber[old]).encode()
            instances.append(NL.join(lines))
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as out:
        out.write(selection['header'].rstrip(NL) + NL)
        for name, tag, blocks in (('MATERIALS', b'MATERIAL', selection['materials']),
                                  ('OBJECTS', b'OBJECT', [selection['bodies'][i] for i in order]),
                                  ('INSTANCES', b'INSTANCE', instances)):
            out.write(NL + b';### ' + name.encode() + b' ###' + NL + str(len(blocks)).encode() + NL)
            for i, body in enumerate(blocks):
                out.write(NL + b';' + tag + b' ' + str(i).encode() + NL + body + NL)
    return path
