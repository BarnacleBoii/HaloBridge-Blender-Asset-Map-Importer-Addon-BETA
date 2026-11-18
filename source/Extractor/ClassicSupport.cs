using System.Reflection;
using System.Text.Json;
using Reclaimer.Blam.Common;
using Reclaimer.Geometry;
using Reclaimer.Utilities;
using H1 = Reclaimer.Blam.Halo1;
using H2 = Reclaimer.Blam.Halo2;

// Halo: CE scenario gameplay blocks (the CE tag layout: 12-byte blocks, 16-byte tag references):
// player starting locations, netgame flags and netgame equipment.
public class H1Gameplay {
 [Reclaimer.IO.Offset(852)] public BlockCollection<H1Start>? Starts { get; set; }
 [Reclaimer.IO.Offset(888)] public BlockCollection<H1Flag>? Flags { get; set; }
 [Reclaimer.IO.Offset(900)] public BlockCollection<H1Equipment>? Equipment { get; set; }
 [Reclaimer.IO.Offset(576)] public BlockCollection<H1Vehicle>? Vehicles { get; set; }
 [Reclaimer.IO.Offset(588)] public BlockCollection<H1PaletteEntry>? VehiclePalette { get; set; }
}
[Reclaimer.IO.FixedSize(120)]
public class H1Vehicle {
 [Reclaimer.IO.Offset(0)] public short Type { get; set; }
 [Reclaimer.IO.Offset(8)] public float X { get; set; }
 [Reclaimer.IO.Offset(12)] public float Y { get; set; }
 [Reclaimer.IO.Offset(16)] public float Z { get; set; }
 [Reclaimer.IO.Offset(20)] public float Yaw { get; set; }  // radians
 [Reclaimer.IO.Offset(24)] public float Pitch { get; set; }
 [Reclaimer.IO.Offset(28)] public float Roll { get; set; }
}
[Reclaimer.IO.FixedSize(48)]
public class H1PaletteEntry {
 [Reclaimer.IO.Offset(0)] public TagReference Tag { get; set; }
}
[Reclaimer.IO.FixedSize(52)]
public class H1Start {
 [Reclaimer.IO.Offset(0)] public float X { get; set; }
 [Reclaimer.IO.Offset(4)] public float Y { get; set; }
 [Reclaimer.IO.Offset(8)] public float Z { get; set; }
 [Reclaimer.IO.Offset(12)] public float Facing { get; set; }  // radians
 [Reclaimer.IO.Offset(16)] public short Team { get; set; }
}
[Reclaimer.IO.FixedSize(148)]
public class H1Flag {
 [Reclaimer.IO.Offset(0)] public float X { get; set; }
 [Reclaimer.IO.Offset(4)] public float Y { get; set; }
 [Reclaimer.IO.Offset(8)] public float Z { get; set; }
 [Reclaimer.IO.Offset(12)] public float Facing { get; set; }
 [Reclaimer.IO.Offset(16)] public short Type { get; set; }
 [Reclaimer.IO.Offset(18)] public short Team { get; set; }
}
[Reclaimer.IO.FixedSize(144)]
public class H1Equipment {
 [Reclaimer.IO.Offset(64)] public float X { get; set; }
 [Reclaimer.IO.Offset(68)] public float Y { get; set; }
 [Reclaimer.IO.Offset(72)] public float Z { get; set; }
 [Reclaimer.IO.Offset(76)] public float Facing { get; set; }
 [Reclaimer.IO.Offset(80)] public TagReference Collection { get; set; }
}

// Halo 2 sky tag (MCC cache: tag references and blocks are 8 bytes): ambient colors, lights
// and global rotation, at the offsets of the Halo 2 Editing Kit's sky definition.
public class H2SkyLighting {
 [Reclaimer.IO.Offset(36)] public float IndoorR { get; set; }
 [Reclaimer.IO.Offset(40)] public float IndoorG { get; set; }
 [Reclaimer.IO.Offset(44)] public float IndoorB { get; set; }
 [Reclaimer.IO.Offset(52)] public float OutdoorR { get; set; }
 [Reclaimer.IO.Offset(56)] public float OutdoorG { get; set; }
 [Reclaimer.IO.Offset(60)] public float OutdoorB { get; set; }
 [Reclaimer.IO.Offset(120)] public BlockCollection<H2SkyLight>? Lights { get; set; }
 [Reclaimer.IO.Offset(128)] public float GlobalRotation { get; set; }
}
[Reclaimer.IO.FixedSize(52)]
public class H2SkyLight {
 [Reclaimer.IO.Offset(12)] public float Yaw { get; set; }
 [Reclaimer.IO.Offset(16)] public float Pitch { get; set; }
 [Reclaimer.IO.Offset(44)] public BlockCollection<H2SkyRadiosity>? Radiosity { get; set; }
}
[Reclaimer.IO.FixedSize(40)]
public class H2SkyRadiosity {
 [Reclaimer.IO.Offset(0)] public int Flags { get; set; }
 [Reclaimer.IO.Offset(4)] public float R { get; set; }
 [Reclaimer.IO.Offset(8)] public float G { get; set; }
 [Reclaimer.IO.Offset(12)] public float B { get; set; }
 [Reclaimer.IO.Offset(16)] public float Power { get; set; }
 [Reclaimer.IO.Offset(36)] public float Diameter { get; set; }
}

// Halo: CE and Halo 2 (MCC) support. These games use different tag layouts from
// Halo 3, but Reclaimer decodes their models, BSPs and shaders into the same
// geometry/material objects, so the JSON written here matches the Halo 3 format.
internal static class ClassicSupport {
 internal static readonly string[] Halo1Shaders={"senv","soso","schi","scex","sotr","swat","sgla","smet","spla"};
 internal static bool IsClassic(ICacheFile cache)=>cache.Metadata.Engine==BlamEngine.Halo1 || (cache.Metadata.Engine==BlamEngine.Halo2 && cache.CacheType>CacheType.Halo2Beta);
 internal static string Game(ICacheFile cache)=>cache.Metadata.Engine==BlamEngine.Halo1?"halo1":"halo2";
 static bool IsH1(ICacheFile cache)=>cache.Metadata.Engine==BlamEngine.Halo1;
 internal static bool IsShader(ICacheFile cache,IIndexItem tag)=>IsH1(cache)?Halo1Shaders.Contains(tag.ClassCode):tag.ClassCode=="shad";
 internal static string ModelClass(ICacheFile cache)=>IsH1(cache)?"mod2":"mode";

 static string? RenderModelOf(ICacheFile cache,IIndexItem scenery) {
  if(IsH1(cache))return scenery.ReadMetadata<H1.SceneryTag>().Model.Tag?.TagName;
  return scenery.ReadMetadata<H2.SceneryTag>().Model.Tag?.ReadMetadata<H2.ModelTag>().RenderModel.Tag?.TagName;
 }

 // Halo: CE baked lighting, for copying onto a Halo 3 level (the add-on's h1_lightmaps): per BSP
 // lightmap block (Halo CE's clusters of one lightmap page) its world positions, normals, lightmap
 // texcoords, incident light directions and triangles, and every lightmap page as PNG. Halo CE keeps
 // a second vertex buffer per material: 20 bytes per vertex, incident direction then texcoord.
 internal static void H1Lightmaps(ICacheFile cache,string output) {
  Directory.CreateDirectory(output);
  var bsps=new List<object>();
  using var reader=cache.CreateReader(cache.DefaultAddressTranslator);
  int bspIndex=0;
  foreach(var tag in cache.TagIndex.Where(t=>t.ClassCode=="sbsp")) {
   var bsp=tag.ReadMetadata<H1.ScenarioStructureBspTag>();
   reader.Seek(bsp.SurfacePointer.Address,SeekOrigin.Begin);
   var indices=reader.ReadArray<ushort>(bsp.SurfaceCount*3);
   var clusters=new List<object>();
   foreach(var block in bsp.Lightmaps) {
    if(block.BitmapIndex<0 || block.Materials.Count==0)continue;
    var pos=new List<float>();var nrm=new List<float>();var uv=new List<float>();var dir=new List<float>();var tri=new List<int>();
    int tally=0;
    foreach(var m in block.Materials) {
     if(m.VertexBuffer2Count!=m.VertexBuffer1Count || m.VertexBuffer1Count==0)continue;
     long a1=cache.Metadata.IsMcc?bsp.MccVertexDataAddress+m.VertexBuffer1Offset:m.VertexBuffer1Pointer.Address;
     long a2=cache.Metadata.IsMcc?bsp.MccVertexDataAddress+m.VertexBuffer2Offset:m.VertexBuffer2Pointer.Address;
     reader.Seek(a1,SeekOrigin.Begin);
     for(int v=0;v<m.VertexBuffer1Count;v++){var b=reader.ReadArray<float>(14);pos.AddRange(new[]{b[0],b[1],b[2]});nrm.AddRange(new[]{b[3],b[4],b[5]});}
     reader.Seek(a2,SeekOrigin.Begin);
     for(int v=0;v<m.VertexBuffer2Count;v++){var b=reader.ReadArray<float>(5);dir.AddRange(new[]{b[0],b[1],b[2]});uv.AddRange(new[]{b[3],b[4]});}
     for(int s=0;s<m.SurfaceCount;s++){int i=(m.SurfaceIndex+s)*3;if(i+2>=indices.Length)break;
      // Halo CE BSP surfaces are wound backwards (as Reclaimer's own BSP reader notes).
      tri.Add(indices[i+2]+tally);tri.Add(indices[i+1]+tally);tri.Add(indices[i]+tally);}
     tally+=m.VertexBuffer1Count;
    }
    if(tally>0)clusters.Add(new{page=(int)block.BitmapIndex,pos,nrm,uv,dir,tri});
   }
   int pageCount=0;
   var pages=Path.Combine(output,"pages"+bspIndex);Directory.CreateDirectory(pages);
   // Halo CE names a BSP's lightmap bitmap after the BSP (levels\test\bloodgulch\bloodgulch); MCC
   // maps no longer keep the reference's id, so the name is the reliable link.
   var bitmapTag=cache.TagIndex.FirstOrDefault(t=>t.ClassCode=="bitm" && t.TagName.Equals(tag.TagName,StringComparison.OrdinalIgnoreCase))
                ??cache.TagIndex.FirstOrDefault(t=>t.ClassCode=="bitm" && bsp.LightmapBitmapId!=0 && (t.Id==(bsp.LightmapBitmapId&0xFFFF) || t.Id==bsp.LightmapBitmapId));
   if(bitmapTag==null)Console.Error.WriteLine("No lightmap bitmap for "+tag.TagName+" (id "+bsp.LightmapBitmapId.ToString("X8")+")");
   if(bitmapTag!=null) {
    var meta=bitmapTag.ReadMetadata<H1.BitmapTag>();
    if(Environment.GetEnvironmentVariable("HB_DEBUG")!=null)foreach(var s in meta.Bitmaps)Console.Error.WriteLine("submap "+s.BitmapFormat+" "+s.Width+"x"+s.Height+" mips "+s.MipmapCount+" flags "+s.Flags+" size "+s.PixelsSize+" offset "+s.PixelsOffset);
    var bitmap=(Reclaimer.Drawing.IBitmap)meta;
    for(int i=0;i<bitmap.SubmapCount;i++) {
     var file=Path.Combine(pages,"lm"+bspIndex+"_"+i.ToString("D2")+"_00.png");
     try{bitmap.ToDds(i).WriteToDisk(file,System.Drawing.Imaging.ImageFormat.Png);pageCount++;}catch(Exception e){Console.Error.WriteLine("Lightmap page "+i+": "+e.Message);}
    }
   }
   bsps.Add(new{tag=tag.TagName,bsp=bspIndex,page_folder="pages"+bspIndex,pages=pageCount,clusters});
   bspIndex++;
  }
  File.WriteAllText(Path.Combine(output,"lightmaps.json"),System.Text.Json.JsonSerializer.Serialize(new{version=1,bsps}));
 }

 // Halo: CE gameplay for the Halo 3 port (the add-on's h1_scenario): player starts, netgame flags
 // and netgame equipment (vehicles) of the map's scenario, as the same JSON h2_scenario produces.
 internal static object H1GameplayData(ICacheFile cache) {
  var tag=cache.TagIndex.GetGlobalTag("scnr");
  var g=tag!.ReadMetadata<H1Gameplay>();
  var deg=180/Math.PI;
  return new{
   starts=(g.Starts?.ToList()??new List<H1Start>()).Select(s=>new{position=new[]{s.X,s.Y,s.Z},facing=s.Facing*deg,team=(int)s.Team}).ToList(),
   flags=(g.Flags?.ToList()??new List<H1Flag>()).Select(f=>new{position=new[]{f.X,f.Y,f.Z},facing=f.Facing*deg,type=(int)f.Type,team=(int)f.Team}).ToList(),
   equipment=(g.Equipment?.ToList()??new List<H1Equipment>()).Select(e=>new{position=new[]{e.X,e.Y,e.Z},facing=e.Facing*deg,collection=e.Collection.Tag?.TagName??""}).ToList(),
   vehicles=(g.Vehicles?.ToList()??new List<H1Vehicle>()).Select(v=>new{tag=v.Type>=0 && g.VehiclePalette!=null && v.Type<g.VehiclePalette.Count?g.VehiclePalette[v.Type].Tag.Tag?.TagName??"":"",position=new[]{v.X,v.Y,v.Z},rotation=new[]{v.Yaw*deg,v.Pitch*deg,v.Roll*deg}}).ToList()
  };
 }

 internal static void Index(ICacheFile cache,string map,string output) {
  var assets=new List<object>();var warnings=new List<string>();
  foreach(var tag in cache.TagIndex) {
   if(IsShader(cache,tag))assets.Add(new{tag=tag.TagName,kind="material",name=tag.FileName,section=-1});
   if(tag.ClassCode==ModelClass(cache))assets.Add(new{tag=tag.TagName,kind="model",name=tag.FileName,section=-1});
   if(tag.ClassCode=="scen") {
    try {var render=RenderModelOf(cache,tag);if(render!=null)assets.Add(new{tag=render,scenery_tag=tag.TagName,kind="scenery",name=tag.FileName,section=-1});}
    catch(Exception e){warnings.Add("Scenery "+tag.TagName+": "+e.Message);}
   }
   if(tag.ClassCode=="sbsp" && !IsH1(cache)) {
    // Halo 2 instanced geometry; Halo CE BSPs have no instances and come in through whole-map import.
    try {
     var model=((IContentProvider<Model>)tag.ReadMetadata<H2.ScenarioStructureBspTag>()).GetContent();
     foreach(var group in model.Regions.SelectMany(r=>r.Permutations).Where(p=>p.IsInstanced)
       .SelectMany(p=>p.MeshIndices.Select(i=>(permutation:p,index:i))).GroupBy(p=>p.index))
      assets.Add(new{tag=tag.TagName,kind="instance",name=group.First().permutation.Name,section=group.Key});
    }catch(Exception e){warnings.Add("BSP "+tag.TagName+": "+e.Message);}
   }
  }
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
  File.WriteAllText(output,JsonSerializer.Serialize(new{version=1,game=Game(cache),map,assets,warnings}));
 }

 static readonly Assembly Blam=typeof(ICacheFile).Assembly;

 // One shader as a Reclaimer material (textures and alpha mode).
 internal static Material? ShaderMaterial(ICacheFile cache,IIndexItem tag) {
  if(IsH1(cache)) {
   using var reader=cache.CreateReader(cache.DefaultAddressTranslator);
   var method=Blam.GetType("Reclaimer.Blam.Halo1.Halo1Common")!.GetMethod("GetMaterials",BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)!;
   var refs=new[]{new TagReference(cache,tag.ClassId,tag.Id)};
   return ((IEnumerable<Material>)method.Invoke(null,new object[]{refs,reader})!).ToList().FirstOrDefault();
  }
  var material=new Material{Id=tag.Id,Name=tag.FileName};
  material.CustomProperties.Add("tag_name",tag.TagName);
  var helper=Blam.GetType("Reclaimer.Blam.Halo2.MaterialHelper")!.GetMethod("PopulateTextureMappings",BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)!;
  helper.Invoke(null,new object[]{new Dictionary<int,H2.BitmapTag>(),material,tag.ReadMetadata<H2.ShaderTag>()});
  return material;
 }

 // The open classic cache, so material writing can fill textures Reclaimer leaves out.
 internal static ICacheFile? Current;

 // Reclaimer reads only some classic shader types: Halo: CE shader_transparent_generic
 // (most sky parts) gets no texture and shader_transparent_chicago only its first map;
 // Halo 2 shaders whose template passes it does not recognise (skies, many effects)
 // lose their bitmaps. When a material has no diffuse texture, its first bitmap is used.
 // Halo 2 shader template and its bitmaps/tiling, so the add-on can recognise
 // camera-sky layers (drawn additively) that Reclaimer reads as opaque.
 internal static void DescribeTemplate(Material material) {
  var cache=Current;
  if(cache!=null && IsH1(cache)){DescribeH1(cache,material);return;}
  if(cache==null || material.CustomProperties.ContainsKey("hb_option_template"))return;
  try {
   var tag=cache.TagIndex.FirstOrDefault(t=>t.Id==material.Id && IsShader(cache,t));
   var props=tag?.ReadMetadata<H2.ShaderTag>().ShaderProperties.FirstOrDefault();
   if(props==null)return;
   var inv=System.Globalization.CultureInfo.InvariantCulture;
   material.CustomProperties.Add("hb_option_template",props.TemplateReference.Tag?.TagName??"");
   material.CustomProperties.Add("hb_option_bitmaps",string.Join("|",props.Bitmaps.Select(b=>b.BitmapReference.Tag?.TagName??"")));
   material.CustomProperties.Add("hb_option_tiling",string.Join("|",props.TilingData.Select(v=>v.X.ToString(inv)+","+v.Y.ToString(inv)+","+v.Z.ToString(inv)+","+v.W.ToString(inv))));
   var template=props.TemplateReference.Tag?.TagName??"";
   if(template.IndexOf(@"\sky_",StringComparison.OrdinalIgnoreCase)>=0)SkyLayer(material,template,props);
   else if(template.IndexOf(@"\transparent\",StringComparison.OrdinalIgnoreCase)>=0 && material.AlphaMode==AlphaMode.Opaque)TransparentLayer(material,template,props);
   else if(template.IndexOf("detail_blend",StringComparison.OrdinalIgnoreCase)>=0)DetailBlend(material,tag!.ReadMetadata<H2.ShaderTag>(),props);
   if(template.IndexOf("alpha_test",StringComparison.OrdinalIgnoreCase)>=0 && template.IndexOf("bump",StringComparison.OrdinalIgnoreCase)>=0)BumpAlphaTest(material);
  } catch(Exception e){Console.Error.WriteLine("Classic shader template "+material.Name+": "+e.Message);}
 }

 // Halo: CE shader class (schi/scex chicago, sotr generic, spla plasma, sgla glass, swat water,
 // smet meter): Reclaimer reads one map of the transparent ones and calls them all "multiply", or
 // none (plasma, generic: drawn black). The add-on uses Halo 3 shaders for plasma, glass and water;
 // chicago, generic and meter layers are mostly glows and lights, drawn additively.
 static readonly string[] H1Additive={"schi","scex","sotr","smet"};
 static void DescribeH1(ICacheFile cache,Material material) {
  if(material.CustomProperties.ContainsKey("hb_option_class"))return;
  var tag=cache.TagIndex.FirstOrDefault(t=>t.Id==material.Id && IsShader(cache,t));
  if(tag==null)return;
  material.CustomProperties.Add("hb_option_class",tag.ClassCode);
  if(H1Additive.Contains(tag.ClassCode)){material.CustomProperties.Add("hb_option_transparent","additive");material.AlphaMode=AlphaMode.Add;}
 }

 // Halo 2 bump-mapped alpha-test templates (tex_bump_alpha_test...) cut out with the bump map's
 // alpha; the base map's alpha holds something else (on Coagulation's banners a torn pattern
 // covering about half the flag). Reclaimer cuts out with the base map's alpha.
 static void BumpAlphaTest(Material material) {
  var bump=material.TextureMappings.FirstOrDefault(t=>t.Usage==TextureUsage.Normal && t.Texture!=null);
  if(bump==null)return;
  bump.Texture.CustomProperties.TryGetValue("tag_name",out var name);
  if((name?.ToString()??"").StartsWith(@"shaders\default_bitmaps",StringComparison.OrdinalIgnoreCase))return;
  material.TextureMappings.RemoveAll(t=>t.Usage==TextureUsage.Transparency);
  material.TextureMappings.Add(new TextureMapping{Usage=TextureUsage.Transparency,Tiling=bump.Tiling,ChannelMask=ChannelMask.Alpha,Texture=bump.Texture});
  if(!material.CustomProperties.ContainsKey("hb_option_alpha_from"))material.CustomProperties.Add("hb_option_alpha_from","bump");
 }

 // Halo 2 "detail_blend" templates (most outdoor ground, e.g. Coagulation's): the base map is
 // stretched once over the level and its alpha blends two detail maps that repeat many times
 // (alpha 0 = the first, 1 = the second). Reclaimer keeps only the stretched base map, which
 // looks blurry up close, so the two detail maps are added here as diffuse_detail with blend
 // channel Red (first) and Green (second). Their tiling rows are the ones the shader pass
 // leaves unnamed, in order.
 static void DetailBlend(Material material,H2.ShaderTag shader,H2.ShaderPropertiesBlock props) {
  var method=Blam.GetType("Reclaimer.Blam.Halo2.MaterialHelper")!.GetMethod("GetTemplateArguments",BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)!;
  var args=new object?[]{shader,null,null,null};
  method.Invoke(null,args);
  var usages=(string?[])args[2]!;var arguments=(string?[])args[3]!;
  var rows=props.TilingData.ToList();
  bool Valid(int row)=>row>=0 && row<rows.Count && rows[row].X>0 && rows[row].Y>0;
  var unnamed=Enumerable.Range(0,Math.Min(rows.Count,arguments.Length)).Where(i=>arguments[i]==null && Valid(i)).ToList();
  int baseRow=Array.IndexOf(arguments,"base_map");
  var baseScale=Valid(baseRow)?new System.Numerics.Vector2(rows[baseRow].X,rows[baseRow].Y):System.Numerics.Vector2.One;
  int baseBitmap=Array.IndexOf(usages,"base_map");
  var names=new[]{"blend_detail_map_1","blend_detail_map_2"};
  var added=new List<TextureMapping>();
  for(int n=0;n<names.Length;n++) {
   // Reclaimer names the bitmaps only for the shader passes it knows; otherwise the two detail
   // maps follow the base map (bump, base, detail 1, detail 2, overlay detail, ...).
   int index=Array.IndexOf(usages,names[n]);
   if(index<0 && baseBitmap>=0)index=baseBitmap+1+n;
   var tag=index>=0 && index<props.Bitmaps.Count?props.Bitmaps[index].BitmapReference.Tag:null;
   if(tag==null || tag.TagName.StartsWith(@"shaders\default_bitmaps",StringComparison.OrdinalIgnoreCase) || tag.TagName.StartsWith(@"rasterizer\",StringComparison.OrdinalIgnoreCase))return;
   // Each bitmap's tiling row has the bitmap's own index when that row is unnamed; else the unnamed rows in order.
   int row=index<arguments.Length && arguments[index]==null && Valid(index)?index:n<unnamed.Count?unnamed[n]:-1;
   var scale=row>=0?new System.Numerics.Vector2(rows[row].X,rows[row].Y):System.Numerics.Vector2.One;
   var texture=new Texture{Id=tag.Id,ContentProvider=tag.ReadMetadata<H2.BitmapTag>()};
   texture.CustomProperties.Add("tag_name",tag.TagName);
   added.Add(new TextureMapping{Usage=TextureUsage.DiffuseDetail,BlendChannel=n==0?ChannelMask.Red:ChannelMask.Green,Tiling=scale*baseScale,Texture=texture});
  }
  material.TextureMappings.RemoveAll(t=>t.Usage==TextureUsage.DiffuseDetail);
  material.TextureMappings.AddRange(added);
  material.CustomProperties.Add("hb_option_detail_blend","1");
 }

 // Other Halo 2 transparent templates (transparent\two_alpha_clouds - Ascension's cloud sea below
 // the level -, transparent\one_add_illum, ...) are see-through layers in the world; Reclaimer does
 // not know them and reads them as opaque, so they drew as solid sheets. "add" templates add their
 // colour, the rest alpha-blend with their map's alpha. A map Reclaimer did not pick up is taken
 // from the shader's first real bitmap.
 static void TransparentLayer(Material material,string template,H2.ShaderPropertiesBlock props) {
  if(!material.TextureMappings.Any(t=>t.Usage==TextureUsage.Diffuse && t.Texture!=null)) {
   var tag=props.Bitmaps.Select(b=>b.BitmapReference.Tag).FirstOrDefault(t=>t!=null && !t.TagName.StartsWith(@"shaders\default_bitmaps",StringComparison.OrdinalIgnoreCase) && !t.TagName.StartsWith(@"rasterizer\",StringComparison.OrdinalIgnoreCase) && t.TagName.IndexOf("cube_map",StringComparison.OrdinalIgnoreCase)<0);
   if(tag==null)return;
   var texture=new Texture{Id=tag.Id,ContentProvider=tag.ReadMetadata<H2.BitmapTag>()};
   texture.CustomProperties.Add("tag_name",tag.TagName);
   material.TextureMappings.Add(new TextureMapping{Usage=TextureUsage.Diffuse,Tiling=System.Numerics.Vector2.One,Texture=texture});
  }
  var name=template.Substring(template.LastIndexOf('\\')+1);
  bool additive=name.IndexOf("add",StringComparison.OrdinalIgnoreCase)>=0;
  material.AlphaMode=additive?AlphaMode.Add:AlphaMode.Blend;
  material.CustomProperties.Add("hb_option_transparent",additive?"additive":"alpha");
 }

 // Halo 2 sky templates (transparent\sky_*) are unlit layers drawn around the camera:
 // "add" templates add their color, the others alpha-blend it. Reclaimer does not know
 // their shader passes, so their bitmaps are mapped here. Each 2D bitmap has a 2-row
 // UV transform (scale in row 0 x, row 1 y), in bitmap order skipping cube maps; any
 // following row is a constant (the tint of "illum" templates).
 static void SkyLayer(Material material,string template,H2.ShaderPropertiesBlock props) {
  var rows=props.TilingData.ToList();
  var real=new List<(IIndexItem tag,System.Numerics.Vector2 scale)>();
  int row=0;
  foreach(var b in props.Bitmaps) {
   var tag=b.BitmapReference.Tag;
   bool cube=tag!=null && tag.TagName.IndexOf("cube_map",StringComparison.OrdinalIgnoreCase)>=0;
   var scale=System.Numerics.Vector2.One;
   if(!cube) {
    if(row+1<rows.Count)scale=new System.Numerics.Vector2(rows[row].X,rows[row+1].Y);
    row+=2;
   }
   if(tag==null || cube || tag.TagName.StartsWith(@"shaders\default_bitmaps",StringComparison.OrdinalIgnoreCase))continue;
   if(!(scale.X>0) || !(scale.Y>0))scale=System.Numerics.Vector2.One;
   real.Add((tag,scale));
  }
  if(real.Count==0)return;
  bool additive=template.IndexOf("_add",StringComparison.OrdinalIgnoreCase)>=0;
  bool clouds=template.IndexOf("clouds",StringComparison.OrdinalIgnoreCase)>=0;
  material.TextureMappings.Clear();
  material.Tints.Clear();
  for(int i=0;i<real.Count && i<2;i++) {
   var (tag,scale)=real[i];
   var texture=new Texture{Id=tag.Id,ContentProvider=tag.ReadMetadata<H2.BitmapTag>()};
   texture.CustomProperties.Add("tag_name",tag.TagName);
   // The second map is the clouds' coverage mask, or a detail map multiplying the color.
   string usage=i==0?TextureUsage.Diffuse:clouds?TextureUsage.Transparency:TextureUsage.DiffuseDetail;
   material.TextureMappings.Add(new TextureMapping{Usage=usage,Tiling=scale,Texture=texture});
  }
  if(template.IndexOf("illum",StringComparison.OrdinalIgnoreCase)>=0 && row<rows.Count) {
   var c=rows[row];
   material.Tints.Add(new MaterialTint{Usage=TintUsage.Albedo,Color=System.Drawing.Color.FromArgb(255,(int)Math.Clamp(c.X*255,0,255),(int)Math.Clamp(c.Y*255,0,255),(int)Math.Clamp(c.Z*255,0,255))});
  }
  material.AlphaMode=additive?AlphaMode.Add:AlphaMode.Blend;
  material.CustomProperties.Add("hb_option_sky",additive?"additive":"alpha");
 }

 // Halo 2 sky lighting (MCC cache layout; Reclaimer reads only the sky's render model).
 // Each light shines from a direction given as yaw/pitch in radians (pitch = height above the
 // horizon), turned by the sky's global rotation; its radiosity block is what Halo 2's
 // lightmapper used: flags (1 exteriors, 2 interiors, 4 direct, 8 indirect), color, power and
 // the angular diameter of the light's disk.
 // renderModel: the sky whose model is this render model (a sky chosen from the asset list);
 // otherwise the scenario's first sky.
 internal static object? SkyLighting(ICacheFile cache,List<string> warnings,string? renderModel=null) {
  try {
   IIndexItem? tag;
   if(renderModel!=null)
    tag=cache.TagIndex.Where(t=>t.ClassCode.Trim()=="sky").FirstOrDefault(t=>{try{return string.Equals(t.ReadMetadata<H2.SkyTag>().RenderModel.Tag?.TagName,renderModel,StringComparison.OrdinalIgnoreCase);}catch{return false;}});
   else {
    var scenario=cache.TagIndex.GetGlobalTag("scnr")?.ReadMetadata<H2.ScenarioTag>();
    tag=scenario?.Skies?.Select(s=>s.SkyReference.Tag).FirstOrDefault(t=>t!=null);
   }
   if(tag==null)return null;
   var sky=tag.ReadMetadata<H2SkyLighting>();
   var lights=new List<object>();
   foreach(var light in sky.Lights??Enumerable.Empty<H2SkyLight>()) {
    double yaw=light.Yaw+sky.GlobalRotation,pitch=light.Pitch;
    var direction=new[]{Math.Cos(pitch)*Math.Cos(yaw),Math.Cos(pitch)*Math.Sin(yaw),Math.Sin(pitch)};
    foreach(var r in light.Radiosity??Enumerable.Empty<H2SkyRadiosity>())
     lights.Add(new{direction,color=new[]{r.R,r.G,r.B},power=r.Power,diameter=r.Diameter,flags=r.Flags});
   }
   return new{sky=tag.TagName,indoor_ambient=new[]{sky.IndoorR,sky.IndoorG,sky.IndoorB},outdoor_ambient=new[]{sky.OutdoorR,sky.OutdoorG,sky.OutdoorB},global_rotation=sky.GlobalRotation,lights};
  } catch(Exception e){warnings.Add("Sky lighting: "+e.Message);return null;}
 }

 internal static void FillMissingDiffuse(Material material) {
  DescribeTemplate(material);
  var cache=Current;
  if(cache==null || material.TextureMappings.Any(t=>t.Usage==TextureUsage.Diffuse && t.Texture!=null))return;
  try {
   var tag=cache.TagIndex.FirstOrDefault(t=>t.Id==material.Id && IsShader(cache,t));
   if(tag==null)return;
   IIndexItem? bitmap;
   if(IsH1(cache))bitmap=FirstH1Bitmap(cache,tag);
   else {
    // Slot 0 is often a placeholder (shaders\default_bitmaps\...); prefer the bitmap Reclaimer
    // already mapped (as transparency), then the first real one.
    var all=tag.ReadMetadata<H2.ShaderTag>().ShaderProperties.SelectMany(p=>p.Bitmaps).Select(b=>b.BitmapReference.Tag).Where(b=>b!=null && !b.TagName.StartsWith(@"shaders\default_bitmaps",StringComparison.OrdinalIgnoreCase)).ToList();
    var mapped=material.TextureMappings.Where(t=>t.Texture!=null).Select(t=>t.Texture.Id).ToHashSet();
    bitmap=all.FirstOrDefault(b=>mapped.Contains(b.Id)) ?? all.FirstOrDefault();
   }
   if(bitmap==null)return;
   var texture=new Texture{Id=bitmap.Id,ContentProvider=IsH1(cache)?bitmap.ReadMetadata<H1.BitmapTag>():bitmap.ReadMetadata<H2.BitmapTag>()};
   texture.CustomProperties.Add("tag_name",bitmap.TagName);  // Reclaimer's source tag property
   // An existing "transparency" map of the same bitmap stays; it is unused while the material is opaque.
   material.TextureMappings.Insert(0,new TextureMapping{Usage=TextureUsage.Diffuse,Tiling=System.Numerics.Vector2.One,Texture=texture});
  } catch(Exception e){Console.Error.WriteLine("Classic shader "+material.Name+": "+e.Message);}
 }

 // Halo: CE tag data lays a tag's blocks out right after its main struct, so the
 // shader's bitmap references are found by scanning to the next tag's data.
 static IIndexItem? FirstH1Bitmap(ICacheFile cache,IIndexItem shader) {
  var bitmapClass=cache.TagIndex.FirstOrDefault(t=>t.ClassCode=="bitm");
  if(bitmapClass==null)return null;
  long start=shader.MetaPointer.Address;
  long next=cache.TagIndex.Select(t=>t.MetaPointer.Address).Where(a=>a>start).DefaultIfEmpty(start+4096).Min();
  int length=(int)Math.Clamp(next-start,0,8192);
  if(length<16)return null;
  using var reader=cache.CreateReader(cache.DefaultAddressTranslator);
  reader.Seek(start,SeekOrigin.Begin);
  var data=reader.ReadBytes(length);  for(int i=0;i+16<=data.Length;i+=4) {
   if(BitConverter.ToInt32(data,i)!=bitmapClass.ClassId)continue;
   int index=BitConverter.ToInt16(data,i+12);
   if(index<0 || index>=cache.TagIndex.TagCount)continue;
   var candidate=cache.TagIndex[index];
   if(candidate!=null && candidate.ClassCode=="bitm")return candidate;
  }
  return null;
 }

 internal static void Material(ICacheFile cache,string path,string output) {
  var tag=cache.TagIndex.First(t=>t.TagName==path && IsShader(cache,t));
  var material=ShaderMaterial(cache,tag) ?? throw new Exception("Shader has no material data: "+path);
  Directory.CreateDirectory(output);
  File.WriteAllText(Path.Combine(output,"preview.json"),JsonSerializer.Serialize(new{version=1,materials=Program.WriteMaterials(new[]{material},output),meshes=Array.Empty<object>()}));
 }
}
