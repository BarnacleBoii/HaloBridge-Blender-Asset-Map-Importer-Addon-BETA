using System.Reflection;
using System.Text.Json;
using Reclaimer.Blam.Common;
using Reclaimer.Geometry;
using Reclaimer.Utilities;
using H4 = Reclaimer.Blam.Halo4;

// Halo 2: Anniversary multiplayer (MCC "groundhog") maps. They use the Halo 4
// engine's tag layouts, which Reclaimer reads with its Halo 4 classes; models,
// BSPs and materials decode into the same objects as the other games.
internal static class H2ASupport {
 internal static bool Is(ICacheFile cache)=>cache.Metadata.Engine==BlamEngine.Halo2X;
 internal const string Game="h2a";
 static readonly Assembly Blam=typeof(ICacheFile).Assembly;

 internal static void Index(ICacheFile cache,string map,string output) {
  var assets=new List<object>();var warnings=new List<string>();
  // The scenario's sky block names its sky scenery; their folders aren't called "sky".
  var skies=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
  try {
   var scenario=cache.TagIndex.GetGlobalTag("scnr")?.ReadMetadata<H4.ScenarioTag>();
   foreach(var sky in scenario?.Skies?? Enumerable.Empty<H4.SkyReferenceBlock>())if(sky.SkyReference.Tag!=null)skies.Add(sky.SkyReference.Tag.TagName);
  }catch(Exception e){warnings.Add("Scenario skies: "+e.Message);}
  foreach(var tag in cache.TagIndex) {
   if(tag.ClassCode=="mat ")assets.Add(new{tag=tag.TagName,kind="material",name=tag.FileName,section=-1});
   if(tag.ClassCode=="mode")assets.Add(new{tag=tag.TagName,kind="model",name=tag.FileName,section=-1});
   if(tag.ClassCode=="scen") {
    try {
     var render=tag.ReadMetadata<H4.SceneryTag>().Model.Tag?.ReadMetadata<H4.ModelTag>().RenderModel.Tag;
     if(render!=null)assets.Add(new{tag=render.TagName,scenery_tag=tag.TagName,kind="scenery",name=tag.FileName,section=-1,sky=skies.Contains(tag.TagName)});
    }catch(Exception e){warnings.Add("Scenery "+tag.TagName+": "+e.Message);}
   }
   if(tag.ClassCode=="sbsp") {
    try {
     var model=((IContentProvider<Model>)tag.ReadMetadata<H4.ScenarioStructureBspTag>()).GetContent();
     foreach(var group in model.Regions.SelectMany(r=>r.Permutations).Where(p=>p.IsInstanced)
       .SelectMany(p=>p.MeshIndices.Select(i=>(permutation:p,index:i))).GroupBy(p=>p.index))
      assets.Add(new{tag=tag.TagName,kind="instance",name=group.First().permutation.Name,section=group.Key});
    }catch(Exception e){warnings.Add("BSP "+tag.TagName+": "+e.Message);}
   }
  }
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
  File.WriteAllText(output,JsonSerializer.Serialize(new{version=1,game=Game,map,assets,warnings}));
 }

 internal static IEnumerable<Material> Materials(ICacheFile cache,IIndexItem tag) {
  var args=new H4.Halo4GeometryArgs{Cache=cache,Shaders=new[]{new H4.ShaderBlock{MaterialReference=new TagReference(cache,tag.ClassId,tag.Id)}}};
  var method=Blam.GetType("Reclaimer.Blam.Halo4.Halo4Common")!.GetMethod("GetMaterials",BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic)!;
  return ((IEnumerable<Material>)method.Invoke(null,new object[]{args})!).Where(m=>m!=null).ToList();
 }

 internal static ICacheFile? Current;
 static readonly Dictionary<string,string> BaseShaders=new(StringComparer.OrdinalIgnoreCase);

 // Cut-out (alpha-tested) material shaders: foliage and the *_clip family clip on
 // the color map's alpha. Reclaimer reads only the blend mode, which is opaque for
 // them. The vertalpha_*_clip shaders clip on vertex alpha instead, so they're left alone.
 internal static bool Clips(string baseShader) {
  var leaf=baseShader.Substring(baseShader.LastIndexOf('\\')+1).ToLowerInvariant();
  if(leaf.Contains("vertalpha")||leaf.Contains("skybox"))return false;
  return leaf.Contains("foliage")||leaf.Contains("_clip")||leaf.Contains("alphamask");
 }

 static string BaseShader(Material m) {
  if(Current==null||!m.CustomProperties.TryGetValue("tag_name",out var name)||name is not string tagName)return "";
  if(BaseShaders.TryGetValue(tagName,out var cached))return cached;
  var result="";
  try {
   var tag=Current.TagIndex.FirstOrDefault(t=>t.ClassCode=="mat " && t.TagName==tagName);
   result=tag?.ReadMetadata<H4.MaterialTag>().BaseShaderReference.Tag?.TagName??"";
  }catch(Exception e){Console.Error.WriteLine("Material "+tagName+": "+e.Message);}
  return BaseShaders[tagName]=result;
 }

 // Applied to every Anniversary material before it's written (assets, models and whole maps).
 internal static void Adjust(Material m) {
  if(Current==null)return;
  var baseShader=BaseShader(m);
  if(baseShader!="" && !m.CustomProperties.ContainsKey("hb_option_material_shader"))m.CustomProperties.Add("hb_option_material_shader",baseShader);
  var unchannelled=m.TextureMappings.Where(t=>t.Usage==TextureUsage.Diffuse && (int)t.BlendChannel==0).ToList();
  // tint_map and similar gradients are read as extra color maps; only the first is the surface color.
  foreach(var extra in unchannelled.Skip(1))m.TextureMappings.Remove(extra);
  if(m.AlphaMode!=AlphaMode.Opaque||!Clips(baseShader)||unchannelled.Count==0)return;
  m.AlphaMode=AlphaMode.Clip;
  var color=unchannelled[0];
  m.TextureMappings.Add(new TextureMapping{Usage=TextureUsage.Transparency,Tiling=color.Tiling,ChannelMask=ChannelMask.Alpha,Texture=color.Texture});
 }

 internal static void Material(ICacheFile cache,string path,string output) {
  var tag=cache.TagIndex.First(t=>t.TagName==path && t.ClassCode=="mat ");
  Directory.CreateDirectory(output);
  File.WriteAllText(Path.Combine(output,"preview.json"),JsonSerializer.Serialize(new{version=1,materials=Program.WriteMaterials(Materials(cache,tag),output),meshes=Array.Empty<object>()}));
 }
}
