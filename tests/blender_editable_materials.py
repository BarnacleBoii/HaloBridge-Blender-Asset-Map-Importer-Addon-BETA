"""Editable material bake/export routing regression; synthetic images only."""
import sys,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from halo_bridge import editable_materials,cross_game,export_review,compat
bpy.ops.mesh.primitive_plane_add();obj=bpy.context.object
base=bpy.data.materials.new('Source');compat.enable_nodes(base)
tex=base.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.new('white',width=4,height=4);tex.image.generated_color=(1,1,1,1)
base.node_tree.links.new(tex.outputs['Color'],base.node_tree.nodes.get('Principled BSDF').inputs['Base Color']);obj.data.materials.append(base)
mat=editable_materials.make(bpy.context,'terrain');mat['hb_bake_size']=512
for name,color in [('Grass',(0,1,0,1)),('Rock',(1,0,0,1)),('Dirt',(0,0,1,1))]:
 image=bpy.data.images.new(name,width=4,height=4);image.generated_color=color;mat.node_tree.nodes[name].image=image
mask=mat.node_tree.nodes['Paint Mask'].image;mask.pixels[:]=[1,0,0,1]*(1024*1024);mask.update()
issues,_,converted=export_review.inspect([obj],{'kit':''});assert not issues,issues
assert mat.as_pointer() in converted
scene=bpy.context.scene
with tempfile.TemporaryDirectory() as folder:
 result=editable_materials.bake(mat,folder)
 image=bpy.data.images.load(result['maps']['base_map']);pixel=image.pixels[:4]
 assert pixel[0]>.9 and pixel[1]<.1 and pixel[2]<.1,pixel
 bpy.data.images.remove(image)
assert bpy.context.scene==scene and obj.active_material==mat
assert base.node_tree.nodes.get('Principled BSDF') is not None
# Layer 4 (blue in the mask), at most four layers.
assert editable_materials.is_paintable_terrain(mat) and editable_materials.terrain_layer_count(mat)==3
editable_materials.add_terrain_layer(mat)
assert editable_materials.terrain_layer_count(mat)==4
try:editable_materials.add_terrain_layer(mat);raise AssertionError('fifth layer allowed')
except ValueError as error:assert 'four' in str(error)
yellow=bpy.data.images.new('Layer4',width=4,height=4);yellow.generated_color=(1,1,0,1);mat.node_tree.nodes['Layer 4'].image=yellow
mat.node_tree.nodes['Rock Tiling'].inputs[1].default_value=(24,12,1)
mask.pixels[:]=[0,0,1,1]*(1024*1024);mask.update()
with tempfile.TemporaryDirectory() as folder:
 result=editable_materials.bake(mat,folder)
 image=bpy.data.images.load(result['maps']['base_map']);pixel=image.pixels[:4]
 assert pixel[0]>.9 and pixel[1]>.9 and pixel[2]<.1,pixel  # the preview shows layer 4
 bpy.data.images.remove(image)
 # Preparation exports a real shader_terrain: full-size tiled layers plus a blend map.
 converted=cross_game.prepare([obj],folder)
 entry=converted[mat.as_pointer()]
 assert entry['terrain'] and entry['name'].startswith('terrain_') and len(entry['layers'])==4,entry
 assert entry['layers'][1]['scale']==[24.0,12.0],entry['layers'][1]
 blend=bpy.data.images.load(entry['maps']['blend_map']);w=blend.pixels[:4]
 assert w[0]<.01 and w[1]<.01 and w[2]<.01 and w[3]>.99,w
 bpy.data.images.remove(blend)
weights=editable_materials.terrain_weights(__import__('numpy').array([[[0,0,0,1],[1,0,0,1],[.5,.5,0,1]]],dtype='float32'),3)
assert abs(weights.sum(axis=2)-1).max()<1e-6 and weights[0,0,0]==1 and weights[0,1,1]==1 and abs(weights[0,2,2]-.5)<1e-6,weights
# Layered editor: black keeps the original blend, red/green/blue/white select layers 1-4,
# and an added layer (channel 0) has no original weight.
np=__import__('numpy')
paint=np.array([[[0,0,0,1],[1,0,0,1],[1,1,1,1]]],dtype='float32')
original=np.array([[[.25,.75,0,1]]*3],dtype='float32')
w=editable_materials.layered_weights(paint,original,[1,2,4,0])
assert np.allclose(w[0,0],[.25,.75,0,0]) and np.allclose(w[0,1],[1,0,0,0]) and np.allclose(w[0,2],[0,0,0,1]),w
obj.data.uv_layers.active.data[0].uv.x=2
issues,_,_=export_review.inspect([obj],{'kit':''});assert '0-1' in str(issues)
print('PASS painted layer bake, routing without stock shader, original material preserved, scene restored, layer 4, shader_terrain export, out-of-tile UV validation')
