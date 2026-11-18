using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Security.Cryptography;
using Bungie;
using Bungie.Tags;

class Job { public int version,section; public float radius; public string operation,kit,scenario,output,template,asset_name; public string[] sources; public float[] position; public ShaderImport[] shaders; public Placement[] placements; public Dictionary<string,string> previous; public SkyLight[] sky_lights; public StartPoint[] starts; public KillVolume[] kill_volumes; public NetObject[] netgame; }
// A multiplayer object (CTF flag spawn, teleporter, hill ...) placed as a crate with multiplayer data.
class NetObject { public string tag; public float[] position; public float yaw,radius,height; public int team,channel,shape; public bool bare; }
// Gameplay from the original map: player starting locations and kill trigger volumes.
class StartPoint { public float[] position; public float facing; public int team; }
class KillVolume { public string name; public float[] position,forward,up,extents; }
class SkyLight { public float[] direction,intensity; public float solid_angle; }
class ShaderImport { public string path,base_map,normal_map,alpha_map,blend_map,blend,detail_map,detail_map2,material; public float[] normal_scale,detail_scale,detail2_scale; public int sort_layer; public bool sky,additive,terrain; public TerrainLayer[] layers; }
class TerrainLayer { public TerrainMap[] maps; }
class TerrainMap { public string usage,bitmap; public float scale_x=1,scale_y=1,offset_x,offset_y; }
class Placement { public Dictionary<string,string> paint; public string id,tag; public float[] position,rotation; public float scale=1; }
class Program {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern bool SetDllDirectory(string p);
 static string kit; static JavaScriptSerializer js=new JavaScriptSerializer {MaxJsonLength=int.MaxValue};
 static int Main(string[] args) {try {
  // ManagedBlam raises .NET assertions on some tags (for example reading a render model's
  // stored source files). Never show the "Assertion Failed" dialog from a background job:
  // write it to the job log instead, and let the caller skip that one item.
  foreach(System.Diagnostics.TraceListener listener in System.Diagnostics.Trace.Listeners) {
   var standard=listener as System.Diagnostics.DefaultTraceListener;
   if(standard!=null)standard.AssertUiEnabled=false;
  }
  System.Diagnostics.Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener(true));
  var j=js.Deserialize<Job>(File.ReadAllText(args[0])); if(j.version!=1)throw new Exception("Unsupported job version");
  kit=Path.GetFullPath(j.kit);SetDllDirectory(kit);Environment.CurrentDirectory=kit;
  AppDomain.CurrentDomain.AssemblyResolve+=(s,e)=>{string p=Path.Combine(kit,"bin",new AssemblyName(e.Name).Name+".dll");return File.Exists(p)?Assembly.LoadFrom(p):null;};
  Assembly.GetExecutingAssembly().GetType("TagOps").GetMethod("Run").Invoke(null,new object[]{j});return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
class TagOps {
 static string kit; static JavaScriptSerializer js=new JavaScriptSerializer {MaxJsonLength=int.MaxValue};
 static T F<T>(TagField[] fields,string name) where T:TagField {return (T)fields.Single(f=>f.FieldName==name);}
 // Object names are plain strings in Halo 3 and ODST, string IDs in Reach.
 static string Text(TagField[] fields,string name) {var f=fields.Single(x=>x.FieldName==name);var plain=f as TagFieldElementStringNormal;if(plain!=null)return plain.Data;var id=f as TagFieldElementStringID;return id!=null?id.Data:"";}
 static TagField[] S(TagField[] fields,string name){return F<TagFieldStruct>(fields,name).Elements[0].Fields;}
 static string Hash(TagFieldBlock b,int i){using(var h=SHA256.Create())return Convert.ToBase64String(h.ComputeHash(b.SerializeElement(i)));}
 static string Safe(string p){if(String.IsNullOrWhiteSpace(p)||Path.IsPathRooted(p)||p.Split('\\','/').Any(x=>x==".."))throw new Exception("Invalid relative tag path");return p.Replace('/','\\');}
 [MethodImpl(MethodImplOptions.NoInlining)] public static void Run(Job j) {
  kit=Path.GetFullPath(j.kit);
  var init=typeof(ManagedBlamSystem).GetMethod("InitializeProject",new[]{typeof(InitializationType),typeof(string)});
  if(init!=null)init.Invoke(null,new object[]{InitializationType.TagsOnly,kit});
  else if(j.operation=="model_collision"||j.operation=="scenario_scene"){var start=typeof(ManagedBlamSystem).GetMethods().Single(m=>m.Name=="Start" && m.GetParameters().Length==3);var t=start.GetParameters()[2].ParameterType;var options=Activator.CreateInstance(t);t.GetProperty("InitializationLevel").SetValue(options,InitializationType.TagsOnly,null);t.GetProperty("ForBackgroundServiceProcess").SetValue(options,true,null);start.Invoke(null,new object[]{kit,null,options});}
  else throw new Exception("Select the Halo 3 Editing Kit for this operation.");
  if(j.operation=="prepare_bitmaps") { PrepareBitmaps(j);return; }
  if(j.operation=="import_shaders") { ImportShaders(j);return; }
  if(j.operation=="list_skies") { ListSkies(j);return; }
  if(j.operation=="dump_tags") { DumpTags(j);return; }
  if(j.operation=="sky_object") { SkyObject(j);return; }
  if(j.operation=="lightmap_policy") { LightmapPolicy(j);return; }
  if(j.operation=="lightmap_mesh") { LightmapMesh(j);return; }
  if(j.operation=="lightmap_write") { LightmapWrite(j);return; }
  if(j.operation=="pervertex_read") { PervertexRead(j);return; }
  if(j.operation=="pervertex_write") { PervertexWrite(j);return; }
  if(j.operation=="recover_source") { RecoverSource(j);return; }
  if(j.operation=="model_collision"){ModelCollision(j);return;}
  if(j.operation=="scenario_scene"){ScenarioScene(j);return;}
  if(j.operation=="collision") { Collision(j);return; }
  if(j.operation=="inspect_bsp") { InspectBsp(j);return; }
  if(j.operation=="resolve_scenery") { ResolveScenery(j);return; }
  if(j.operation=="resolve_vehicles") { ResolveVehicles(j);return; }
  if(j.operation=="copy_level") { CopyLevel(j);return; }
  if(j.operation=="verify_base") { VerifyCopiedScenario(Safe(j.template),Safe(j.scenario),true);File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,original_gameplay_verified=true}));return; }
  if(j.operation=="verify_copy") { VerifyCopiedScenario(Safe(j.template),Safe(j.scenario));File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,scenario_data_verified=true}));return; }
  var path=TagPath.FromPathAndType(Safe(j.scenario),"scnr*");
  using(var tag=new TagFile(path)) {
   var scenery=F<TagFieldBlock>(tag.Fields,"scenery");var palette=F<TagFieldBlock>(tag.Fields,"scenery palette");var names=F<TagFieldBlock>(tag.Fields,"object names");
   var owned=new Dictionary<string,int>();
   for(int i=0;i<scenery.Elements.Count;i++) {int ni=F<TagFieldBlockIndex>(scenery.Elements[i].Fields,"name").Value;if(ni>=0 && ni<names.Elements.Count) {string n=F<TagFieldElementStringNormal>(names.Elements[ni].Fields,"name").Data;if(n.StartsWith("hb_")){if(owned.ContainsKey(n))throw new Exception("Duplicate managed placement name: "+n);owned[n]=i;}}}
   if(j.operation=="sync_vehicles") { SyncVehicles(tag,j);tag.Save();
   } else if(j.operation=="sync") {
    var prev=(j.previous??new Dictionary<string,string>()).Where(p=>!p.Key.StartsWith("vehicle:")).ToDictionary(p=>p.Key,p=>p.Value);
    foreach(var pair in prev) if(!owned.ContainsKey(pair.Key)||Hash(scenery,owned[pair.Key])!=pair.Value)throw new Exception("CONFLICT: Sapien changed or removed Blender placement "+pair.Key+". Restore it or explicitly resolve ownership before exporting.");
    foreach(var pair in owned)if(!prev.ContainsKey(pair.Key))throw new Exception("CONFLICT: Untracked Blender placement "+pair.Key);
    var placements=j.placements??new Placement[0];
    if(placements.Select(p=>p.id).Distinct().Count()!=placements.Length)throw new Exception("Duplicate placement IDs");
    foreach(var p in placements) {if(!p.id.StartsWith("hb_")||p.id.Length>31||p.position.Length!=3||p.rotation.Length!=3||p.scale<=0||p.position.Concat(p.rotation).Concat(new[]{p.scale}).Any(x=>float.IsNaN(x)||float.IsInfinity(x)))throw new Exception("Invalid placement");if(!File.Exists(Path.Combine(kit,"tags",Safe(p.tag)+".scenery")))throw new Exception("Missing scenery tag: "+p.tag);}
    var wanted=new HashSet<string>(placements.Select(p=>p.id));
    foreach(var pair in owned.Where(p=>!wanted.Contains(p.Key)).OrderByDescending(p=>p.Value)) {int ni=F<TagFieldBlockIndex>(scenery.Elements[pair.Value].Fields,"name").Value;scenery.RemoveElement(pair.Value);F<TagFieldBlockIndex>(names.Elements[ni].Fields,"scenario_datum_index").Value=-1;}
    owned.Clear();
    for(int i=0;i<scenery.Elements.Count;i++){int ni=F<TagFieldBlockIndex>(scenery.Elements[i].Fields,"name").Value;if(ni>=0 && ni<names.Elements.Count)owned[F<TagFieldElementStringNormal>(names.Elements[ni].Fields,"name").Data]=i;}
    foreach(var p in placements) {
     int pi=-1;for(int i=0;i<palette.Elements.Count;i++){var r=F<TagFieldReference>(palette.Elements[i].Fields,"name").Path;if(r!=null && r.RelativePath.Equals(p.tag,StringComparison.OrdinalIgnoreCase))pi=i;}
     if(pi<0){pi=palette.Elements.Count;F<TagFieldReference>(palette.AddElement().Fields,"name").Path=TagPath.FromPathAndType(Safe(p.tag),"scen*");}
     int si;TagField[] f;
     if(owned.TryGetValue(p.id,out si))f=scenery.Elements[si].Fields;
     else {si=scenery.Elements.Count;f=scenery.AddElement().Fields;int ni=names.Elements.Count;var nf=names.AddElement().Fields;F<TagFieldElementStringNormal>(nf,"name").Data=p.id;F<TagFieldBlockIndex>(nf,"object_type").Value=6;F<TagFieldBlockIndex>(nf,"scenario_datum_index").Value=si;F<TagFieldBlockIndex>(f,"name").Value=ni;
      var d=S(f,"object data");var oid=S(d,"object id");F<TagFieldElementInteger>(oid,"unique id").Data=Convert.ToInt32(p.id.Substring(3,7),16);F<TagFieldEnum>(oid,"type").Value=6;F<TagFieldEnum>(oid,"source").Value=1;F<TagFieldBlockIndex>(oid,"origin bsp index").Value=-1;
     }
     F<TagFieldBlockIndex>(f,"type").Value=pi;var data=S(f,"object data");F<TagFieldElementArraySingle>(data,"position").Data=p.position;F<TagFieldElementArraySingle>(data,"rotation").Data=p.rotation;F<TagFieldElementSingle>(data,"scale").Data=p.scale;
    }
    // Reconcile name indices after scenery deletions, including Sapien-owned names.
    for(int i=0;i<scenery.Elements.Count;i++){int ni=F<TagFieldBlockIndex>(scenery.Elements[i].Fields,"name").Value;if(ni>=0)F<TagFieldBlockIndex>(names.Elements[ni].Fields,"scenario_datum_index").Value=i;}
    tag.Save();
   } else if(j.operation=="ensure_spawn") {
    var starts=F<TagFieldBlock>(tag.Fields,"player starting locations");
    if(starts.Elements.Count==0) {
     if(j.position==null || j.position.Length!=3 || j.position.Any(x=>Single.IsNaN(x)||Single.IsInfinity(x)))throw new Exception("Invalid test spawn position");
     starts.AddElement();var fields=starts.Elements[0].Fields;
     F<TagFieldElementArraySingle>(fields,"position").Data=j.position;
     // Halo 3 names the BSP; ODST has an insertion point index instead (0 for both).
     foreach(var name in new[]{"bsp index","insertion point index"}){var index=fields.FirstOrDefault(f=>f.FieldName==name) as TagFieldElementInteger;if(index!=null)index.Data=0;}
     tag.Save();
    }
   } else if(j.operation=="gameplay") {
    Gameplay(tag,j);tag.Save();
   } else if(j.operation=="environment") {
    using(var donor=new TagFile(TagPath.FromPathAndType(Safe(j.template),"scnr*"))) {
     var originalSkies=F<TagFieldBlock>(donor.Fields,"skies");var destinationSkies=F<TagFieldBlock>(tag.Fields,"skies");
     if(originalSkies.Elements.Count==0)throw new Exception("The chosen map has no sky references.");
     var chosen=AllReferences(originalSkies.Elements[0].Fields).FirstOrDefault(r=>r.Path!=null);
     if(chosen==null || !File.Exists(chosen.Path.Filename))throw new Exception("The chosen map sky tag is missing.");
     if(destinationSkies.Elements.Count==0) {
      while(originalSkies.Elements.Count>1)originalSkies.RemoveElement(originalSkies.Elements.Count-1);
      destinationSkies.DeserializeEntireBlock(originalSkies.SerializeEntireBlock());
     } else {
      // Keep existing slots/BSP masks so all BSP sky indices stay valid.
      foreach(var element in destinationSkies.Elements) {
       var reference=AllReferences(element.Fields).Single(r=>r.FieldName==chosen.FieldName);reference.Path=chosen.Path;
      }
     }
    }tag.Save();
   } else if(j.operation!="inspect")throw new Exception("Unknown operation");
  }
  using(var tag=new TagFile(path)) {
   var scenery=F<TagFieldBlock>(tag.Fields,"scenery");var names=F<TagFieldBlock>(tag.Fields,"object names");var state=new Dictionary<string,string>();var items=new List<object>();
   for(int i=0;i<scenery.Elements.Count;i++){var f=scenery.Elements[i].Fields;int ni=F<TagFieldBlockIndex>(f,"name").Value;string n=ni>=0?F<TagFieldElementStringNormal>(names.Elements[ni].Fields,"name").Data:"";if(n.StartsWith("hb_"))state[n]=Hash(scenery,i);var d=S(f,"object data");items.Add(new{name=n,position=F<TagFieldElementArraySingle>(d,"position").Data,rotation=F<TagFieldElementArraySingle>(d,"rotation").Data,scale=F<TagFieldElementSingle>(d,"scale").Data});}
   var spawns=F<TagFieldBlock>(tag.Fields,"player starting locations");
   var vehicles=F<TagFieldBlock>(tag.Fields,"vehicles");var vp=F<TagFieldBlock>(tag.Fields,"vehicle palette");var vehicleItems=new List<object>();
   foreach(var pair in VehicleOwned(vehicles,names))state["vehicle:"+pair.Key]=VehicleHash(vehicles,vp,pair.Value);
   for(int i=0;i<vehicles.Elements.Count;i++){var f=vehicles.Elements[i].Fields;var d=S(f,"object data");int pi=F<TagFieldBlockIndex>(f,"type").Value;int ni=F<TagFieldBlockIndex>(f,"name").Value;vehicleItems.Add(new{name=ni>=0&&ni<names.Elements.Count?F<TagFieldElementStringNormal>(names.Elements[ni].Fields,"name").Data:"",tag=VehicleTag(vehicles,vp,i),position=F<TagFieldElementArraySingle>(d,"position").Data,rotation=F<TagFieldElementArraySingle>(d,"rotation").Data,scale=F<TagFieldElementSingle>(d,"scale").Data});}
   File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,state=state,placements=items,vehicles=vehicleItems,scenery_count=scenery.Elements.Count,skies=AllReferences(F<TagFieldBlock>(tag.Fields,"skies").Elements.Cast<TagElement>().SelectMany(e=>e.Fields).ToArray()).Where(r=>r.Path!=null).Select(r=>r.Path.RelativePathWithExtension).ToArray(),spawn_count=spawns.Elements.Count,spawns=Convert.ToBase64String(spawns.SerializeEntireBlock())}));Console.WriteLine("Scenario tags verified");
  }
 }
 static Dictionary<string,int> VehicleOwned(TagFieldBlock block,TagFieldBlock names) {
  var result=new Dictionary<string,int>();
  for(int i=0;i<block.Elements.Count;i++){int ni=F<TagFieldBlockIndex>(block.Elements[i].Fields,"name").Value;if(ni<0||ni>=names.Elements.Count)continue;string name=F<TagFieldElementStringNormal>(names.Elements[ni].Fields,"name").Data;if(name.StartsWith("hb_")){if(result.ContainsKey(name))throw new Exception("Duplicate managed vehicle name: "+name);result.Add(name,i);}}
  return result;
 }
 static string VehicleHash(TagFieldBlock block,TagFieldBlock palette,int index) {
  return Hash(block,index)+":"+VehicleTag(block,palette,index);
 }
 static string VehicleTag(TagFieldBlock block,TagFieldBlock palette,int index) {
  int pi=F<TagFieldBlockIndex>(block.Elements[index].Fields,"type").Value;
  if(pi<0||pi>=palette.Elements.Count)return "";
  var reference=F<TagFieldReference>(palette.Elements[pi].Fields,"name").Path;
  return reference==null?"":reference.RelativePath;
 }
 static string PaintedVehicle(Job job, Placement p) {
  string basePath=Path.GetDirectoryName(Safe(job.scenario))+"\\vehicles\\"+p.id;
  string shaderRoot=Path.GetDirectoryName(Safe(job.scenario))+"\\shaders\\";
  var missing=new HashSet<string>(p.paint.Keys,StringComparer.OrdinalIgnoreCase);
  Directory.CreateDirectory(Path.Combine(kit,"tags",Path.GetDirectoryName(basePath)));
  using(var vehicle=new TagFile(TagPath.FromPathAndType(Safe(p.tag),"vehi*"))) {
   var modelRef=References(vehicle.Fields).Single(r=>r.FieldName=="model" && r.Path!=null);
   using(var model=new TagFile(modelRef.Path)) {
    var renderRef=References(model.Fields).Single(r=>r.FieldName=="render model" && r.Path!=null);
    using(var render=new TagFile(renderRef.Path)) {
     var materials=F<TagFieldBlock>(render.Fields,"materials");
     foreach(var item in materials.Elements) {
      foreach(var reference in References(item.Fields)) {
       string alias;
       if(reference.Path==null || !reference.Path.Extension.StartsWith("shader") || !p.paint.TryGetValue(reference.Path.RelativePath,out alias))continue;
       if(!System.Text.RegularExpressions.Regex.IsMatch(alias,"^custom_[0-9a-f]{20}$") || !File.Exists(Path.Combine(kit,"tags",shaderRoot+alias+".shader")))throw new Exception("Missing generated vehicle paint shader: "+alias);
       missing.Remove(reference.Path.RelativePath);
       reference.Path=TagPath.FromPathAndType(shaderRoot+alias,"rmsh");
      }
     }
     if(missing.Count>0)throw new Exception("Vehicle render model has no matching shader for: "+String.Join(", ",missing));
     var newRender=TagPath.FromPathAndType(basePath,"mode");
     render.SaveAs(newRender);renderRef.Path=newRender;
    }
    var newModel=TagPath.FromPathAndType(basePath,"hlmt*");
    model.SaveAs(newModel);modelRef.Path=newModel;
   }
   vehicle.SaveAs(TagPath.FromPathAndType(basePath,"vehi*"));
  }
  return basePath;
 }
 static void SyncVehicles(TagFile tag,Job j) {
  var block=F<TagFieldBlock>(tag.Fields,"vehicles");var palette=F<TagFieldBlock>(tag.Fields,"vehicle palette");var names=F<TagFieldBlock>(tag.Fields,"object names");var owned=VehicleOwned(block,names);
  var prev=(j.previous??new Dictionary<string,string>()).Where(p=>p.Key.StartsWith("vehicle:")).ToDictionary(p=>p.Key.Substring(8),p=>p.Value);
  foreach(var pair in prev)if(!owned.ContainsKey(pair.Key)||VehicleHash(block,palette,owned[pair.Key])!=pair.Value)throw new Exception("CONFLICT: Sapien changed or removed Blender vehicle "+pair.Key);
  foreach(var pair in owned)if(!prev.ContainsKey(pair.Key))throw new Exception("CONFLICT: Untracked Blender vehicle "+pair.Key);
  var placements=j.placements??new Placement[0];if(placements.Select(p=>p.id).Distinct().Count()!=placements.Length)throw new Exception("Duplicate vehicle placement IDs");
  foreach(var p in placements){if(p.id==null||!System.Text.RegularExpressions.Regex.IsMatch(p.id,"^hb_[0-9a-f]{24}$")||p.position==null||p.rotation==null||p.position.Length!=3||p.rotation.Length!=3||p.scale<=0||p.position.Concat(p.rotation).Concat(new[]{p.scale}).Any(x=>float.IsNaN(x)||float.IsInfinity(x)))throw new Exception("Invalid vehicle placement");if(!File.Exists(Path.Combine(kit,"tags",Safe(p.tag)+".vehicle")))throw new Exception("Missing vehicle tag: "+p.tag);}
  var wanted=new HashSet<string>(placements.Select(p=>p.id));
  foreach(var pair in owned.Where(p=>!wanted.Contains(p.Key)).OrderByDescending(p=>p.Value)){int ni=F<TagFieldBlockIndex>(block.Elements[pair.Value].Fields,"name").Value;block.RemoveElement(pair.Value);F<TagFieldBlockIndex>(names.Elements[ni].Fields,"scenario_datum_index").Value=-1;}
  owned=VehicleOwned(block,names);
  foreach(var p in placements){
   if(p.paint!=null && p.paint.Count>0)p.tag=PaintedVehicle(j,p);
   int pi=-1;for(int i=0;i<palette.Elements.Count;i++){var r=F<TagFieldReference>(palette.Elements[i].Fields,"name").Path;if(r!=null&&r.RelativePath.Equals(p.tag,StringComparison.OrdinalIgnoreCase))pi=i;}
   if(pi<0){pi=palette.Elements.Count;F<TagFieldReference>(palette.AddElement().Fields,"name").Path=TagPath.FromPathAndType(Safe(p.tag),"vehi*");}
   int index;TagField[] fields;
   if(owned.TryGetValue(p.id,out index))fields=block.Elements[index].Fields;
   else {
    // Never reuse an independently owned name or silently change another object type.
    if(names.Elements.Cast<TagElement>().Any(e=>F<TagFieldElementStringNormal>(e.Fields,"name").Data==p.id&&F<TagFieldBlockIndex>(e.Fields,"scenario_datum_index").Value>=0))throw new Exception("Vehicle name is already in use: "+p.id);
    index=block.Elements.Count;fields=block.AddElement().Fields;int ni=names.Elements.Count;var nf=names.AddElement().Fields;
    F<TagFieldElementStringNormal>(nf,"name").Data=p.id;F<TagFieldBlockIndex>(nf,"object_type").Value=1;F<TagFieldBlockIndex>(nf,"scenario_datum_index").Value=index;F<TagFieldBlockIndex>(fields,"name").Value=ni;
    var data=S(fields,"object data");var oid=S(data,"object id");F<TagFieldElementInteger>(oid,"unique id").Data=Convert.ToInt32(p.id.Substring(3,7),16);F<TagFieldEnum>(oid,"type").Value=1;F<TagFieldEnum>(oid,"source").Value=1;F<TagFieldBlockIndex>(oid,"origin bsp index").Value=-1;
    F<TagFieldBlockIndex>(data,"editor folder").Value=-1;F<TagFieldBlockIndex>(S(data,"parent id"),"parent object").Value=-1;
    F<TagFieldElementSingle>(S(fields,"unit data"),"body vitality").Data=1;
    var multi=S(fields,"multiplayer data");F<TagFieldEnum>(multi,"owner team").Value=8;F<TagFieldElementInteger>(multi,"quota maximum").Data=1;F<TagFieldBlockIndex>(S(multi,"map variant parent"),"parent object").Value=-1;
   }
   F<TagFieldBlockIndex>(fields,"type").Value=pi;var d=S(fields,"object data");F<TagFieldElementArraySingle>(d,"position").Data=p.position;F<TagFieldElementArraySingle>(d,"rotation").Data=p.rotation;F<TagFieldElementSingle>(d,"scale").Data=p.scale;
  }
  for(int i=0;i<block.Elements.Count;i++){int ni=F<TagFieldBlockIndex>(block.Elements[i].Fields,"name").Value;if(ni>=0)F<TagFieldBlockIndex>(names.Elements[ni].Fields,"scenario_datum_index").Value=i;}
 }
 static void ResolveVehicles(Job j) {
  var wanted=new HashSet<string>((j.sources??new string[0]).Select(Safe),StringComparer.OrdinalIgnoreCase);var matches=new List<object>();var errors=new List<string>();string root=Path.Combine(kit,"tags");
  foreach(string file in Directory.EnumerateFiles(root,"*.vehicle",SearchOption.AllDirectories)) {
   string source=file.Substring(root.Length+1);source=source.Substring(0,source.Length-8);
   try {using(var vehicle=new TagFile(TagPath.FromPathAndType(source,"vehi*"))) {
    var model=References(vehicle.Fields).FirstOrDefault(r=>r.FieldName=="model"&&r.Path!=null);if(model==null)continue;
    using(var modelTag=new TagFile(model.Path)) {var render=References(modelTag.Fields).FirstOrDefault(r=>r.FieldName=="render model"&&r.Path!=null);if(render!=null&&wanted.Contains(render.Path.RelativePath))matches.Add(new{render=render.Path.RelativePath,vehicle=source});}
   }}catch(Exception e){errors.Add(source+": "+e.Message);}
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,matches=matches,warnings=errors}));
 }
 static void PrepareBitmaps(Job j) {
  string prefix=Path.GetDirectoryName(Safe(j.scenario))+"\\bitmaps\\reach\\";
  foreach(var item in j.shaders??new ShaderImport[0]) {
   var bitmaps=new List<KeyValuePair<string,string>>{new KeyValuePair<string,string>("base",item.base_map),new KeyValuePair<string,string>("normal",item.normal_map),new KeyValuePair<string,string>("alpha",item.alpha_map),new KeyValuePair<string,string>("blend",item.blend_map),new KeyValuePair<string,string>("base",item.detail_map),new KeyValuePair<string,string>("base",item.detail_map2)};
   foreach(var layer in item.layers??new TerrainLayer[0])foreach(var map in layer.maps??new TerrainMap[0])bitmaps.Add(new KeyValuePair<string,string>(map.usage=="bump"?"normal":"base",map.bitmap));
   foreach(var pair in bitmaps) {
   if(String.IsNullOrEmpty(pair.Value))continue;
   string target=Safe(pair.Value);
   if(!target.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new Exception("Converted bitmap is outside this level.");
   var path=TagPath.FromPathAndType(target,"bitm");
   using(var tag=new TagFile()) {
    if(File.Exists(Path.Combine(kit,"tags",target+".bitmap")))tag.Load(path);else tag.New(path);
    // Usage 18 is "Blend Map (linear for terrains)", also right for alpha-test masks.
    F<TagFieldEnum>(tag.Fields,"Usage").Value=pair.Key=="normal"?13:pair.Key=="alpha"||pair.Key=="blend"?18:0;
    F<TagFieldEnum>(tag.Fields,"force bitmap format").Value=2;
    F<TagFieldEnum>(tag.Fields,"curve mode").Value=pair.Key=="base"?2:1;
    Directory.CreateDirectory(Path.GetDirectoryName(Path.Combine(kit,"tags",target)));
    tag.Save();
   }
   }
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true}));
 }
 static void ImportShaders(Job j) {
  // Level shaders sit in <level>\shaders, converted sky shaders in <level>\sky\shaders.
  string level=Path.GetDirectoryName(Safe(j.scenario))+"\\";
  var verified=new List<object>();
  foreach(var item in j.shaders??new ShaderImport[0]) {
   string target=Safe(item.path);
   if(!target.StartsWith(level+"shaders\\",StringComparison.OrdinalIgnoreCase) && !target.StartsWith(level+"sky\\shaders\\",StringComparison.OrdinalIgnoreCase))throw new Exception("Generated shader is outside this level.");
   if(item.terrain){verified.Add(TerrainShader(item,target));continue;}
   using(var tag=new TagFile(TagPath.FromPathAndType("shaders\\invalid","rmsh"))) {
    var fields=S(tag.Fields,"render_method");
    var options=F<TagFieldBlock>(fields,"options");
    for(int i=0;i<options.Elements.Count;i++)F<TagFieldElementInteger>(options.Elements[i].Fields,"short").Data=0;
    F<TagFieldElementInteger>(options.Elements[1].Fields,"short").Data=String.IsNullOrEmpty(item.normal_map)?0:1;
    F<TagFieldElementInteger>(options.Elements[2].Fields,"short").Data=String.IsNullOrEmpty(item.alpha_map)?0:1;
    F<TagFieldElementInteger>(options.Elements[9].Fields,"short").Data=1;
    // Converted skies have no sky lighting, so their shaders are unlit (material model
    // "none") and show their texture as self-illumination ("from_diffuse").
    // Halo 2 see-through world layers (blend "alpha"/"additive" outside the sky) are unlit the same way.
    bool layer=item.sky || item.additive || item.blend=="alpha";
    if(layer){F<TagFieldElementInteger>(options.Elements[1].Fields,"short").Data=0;F<TagFieldElementInteger>(options.Elements[4].Fields,"short").Data=4;F<TagFieldElementInteger>(options.Elements[6].Fields,"short").Data=4;}
    // blend_mode "additive" (Halo CE / Halo 2 sky layers, Halo 2 glows); alpha test does not apply to it.
    if(item.additive){F<TagFieldElementInteger>(options.Elements[7].Fields,"short").Data=1;F<TagFieldElementInteger>(options.Elements[2].Fields,"short").Data=0;}
    // blend_mode "alpha_blend" (Halo 2 sky layers, Ascension's cloud sea): the base map's alpha is the coverage.
    if(item.blend=="alpha"){F<TagFieldElementInteger>(options.Elements[7].Fields,"short").Data=3;F<TagFieldElementInteger>(options.Elements[2].Fields,"short").Data=0;}
    // Albedo "detail_blend" (Halo 2 detail_blend ground): the base map's alpha blends detail_map
    // (alpha 0) and detail_map2 (alpha 1); "default" multiplies one detail_map over the base.
    if(!item.sky && !String.IsNullOrEmpty(item.detail_map) && !String.IsNullOrEmpty(item.detail_map2))F<TagFieldElementInteger>(options.Elements[0].Fields,"short").Data=1;
    // Sort layer (1 pre-pass, 2 normal, 3 post-pass): keeps a Halo 2 sky's layer order.
    if(item.sort_layer>=1 && item.sort_layer<=3)F<TagFieldEnum>(fields,"sort layer").Value=item.sort_layer;
    var parameters=F<TagFieldBlock>(fields,"parameters");while(parameters.Elements.Count>0)parameters.RemoveElement(parameters.Elements.Count-1);
    var maps=new List<Tuple<string,string,float[]>>{Tuple.Create("base_map",item.base_map,(float[])null),Tuple.Create("bump_map",item.normal_map,item.normal_scale),Tuple.Create("alpha_test_map",item.alpha_map,(float[])null)};
    if(!item.sky){maps.Add(Tuple.Create("detail_map",item.detail_map,item.detail_scale));if(!String.IsNullOrEmpty(item.detail_map))maps.Add(Tuple.Create("detail_map2",item.detail_map2,item.detail2_scale));}
    foreach(var map in maps) {
     if(String.IsNullOrEmpty(map.Item2))continue;
     string bitmap=Safe(map.Item2);
     if(!File.Exists(Path.Combine(kit,"tags",bitmap+".bitmap")))throw new Exception("Converted bitmap missing: "+bitmap);
     var scale=map.Item3!=null && map.Item3.Length==2 && map.Item3.All(x=>x>0 && !float.IsInfinity(x))?map.Item3:new float[]{1,1};
     BitmapParameter(parameters,map.Item1,bitmap,scale[0],scale[1]);
    }
    SetMaterial(tag.Fields,item.material);
    Directory.CreateDirectory(Path.GetDirectoryName(Path.Combine(kit,"tags",target)));
    tag.SaveAs(TagPath.FromPathAndType(target,"rmsh"));
   }
   using(var tag=new TagFile(TagPath.FromPathAndType(target,"rmsh"))) {
    var references=AllReferences(tag.Fields).Where(r=>r.Path!=null).Select(r=>r.Path.RelativePathWithExtension).ToArray();
    if(!references.Contains(item.base_map+".bitmap"))throw new Exception("Generated shader lost its base texture.");
    verified.Add(new{shader=target,references=references});
   }
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,shaders=verified}));
 }
 // The shader's global material (globals "materials"): Halo 3 takes the surface's footstep sounds,
 // impact effects and decals from it. Generated shaders otherwise keep "default_material".
 static void SetMaterial(TagField[] fields,string material) {
  if(String.IsNullOrEmpty(material))return;
  var field=fields.FirstOrDefault(f=>f.FieldName=="material name");if(field==null)return;
  var data=field.GetType().GetProperty("Data");if(data!=null && data.CanWrite)data.SetValue(field,material,null);
 }
 // A constant animated-parameter function (as Guerilla stores one): type 1, flags 0x20, value.
 static byte[] ConstantFunction(float value) {
  var data=new byte[32];data[0]=1;data[1]=0x20;
  BitConverter.GetBytes(value).CopyTo(data,4);BitConverter.GetBytes(value).CopyTo(data,8);
  return data;
 }
 static void BitmapParameter(TagFieldBlock parameters,string name,string bitmap,float scaleX,float scaleY,float offsetX=0,float offsetY=0) {
  if(!File.Exists(Path.Combine(kit,"tags",bitmap+".bitmap")))throw new Exception("Terrain bitmap missing: "+bitmap);
  var f=parameters.AddElement().Fields;
  F<TagFieldElementStringID>(f,"parameter name").Data=name;
  F<TagFieldEnum>(f,"parameter type").Value=0;
  F<TagFieldReference>(f,"bitmap").Path=TagPath.FromPathAndType(bitmap,"bitm");
  var animated=F<TagFieldBlock>(f,"animated parameters");
  // 3/4 = scale x/y (repeats across the UV tile), 5/6 = translation x/y: uv * scale + translation.
  var values=new List<KeyValuePair<int,float>>();
  if(scaleX!=1 || scaleY!=1){values.Add(new KeyValuePair<int,float>(3,scaleX));values.Add(new KeyValuePair<int,float>(4,scaleY));}
  if(offsetX!=0)values.Add(new KeyValuePair<int,float>(5,offsetX));
  if(offsetY!=0)values.Add(new KeyValuePair<int,float>(6,offsetY));
  foreach(var axis in values) {
   var a=animated.AddElement().Fields;
   F<TagFieldEnum>(a,"type").Value=axis.Key;
   F<TagFieldData>(S(a,"function"),"data").SetData(ConstantFunction(axis.Value));
  }
 }
 static object TerrainShader(ShaderImport item,string target) {
  // Halo 3 shader_terrain: blend map channels R/G/B/A weight material_0..3. Each
  // material is base_map (the layer texture, tiled) times a neutral 50% gray detail
  // map, so colors match the layer images (the shader multiplies by 4.59 = 1/0.5^2.2).
  var layers=item.layers??new TerrainLayer[0];
  if(layers.Length<1 || layers.Length>4)throw new Exception("A terrain shader needs 1 to 4 layers.");
  if(String.IsNullOrEmpty(item.blend_map))throw new Exception("The terrain blend map is missing.");
  var path=TagPath.FromPathAndType(target,"rmtr");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.Combine(kit,"tags",target)));
  using(var tag=new TagFile()) {
   tag.New(path);
   var fields=S(tag.Fields,"render_method");
   F<TagFieldReference>(fields,"definition").Path=TagPath.FromPathAndType("shaders\\terrain","rmdf");
   var options=F<TagFieldBlock>(fields,"options");
   while(options.Elements.Count>0)options.RemoveElement(options.Elements.Count-1);
   // blending, environment_map, material_0..3 (0 = diffuse_only, 2 = off).
   for(int i=0;i<6;i++){var o=options.AddElement().Fields;F<TagFieldElementInteger>(o,"short").Data=i>=2 && i-2>=layers.Length?2:0;}
   var parameters=F<TagFieldBlock>(fields,"parameters");
   while(parameters.Elements.Count>0)parameters.RemoveElement(parameters.Elements.Count-1);
   BitmapParameter(parameters,"blend_map",Safe(item.blend_map),1,1);
   for(int i=0;i<layers.Length;i++) {
    var maps=layers[i].maps??new TerrainMap[0];
    if(!maps.Any(m=>m.usage=="base"))throw new Exception("Terrain layer "+(i+1)+" has no texture.");
    foreach(var map in maps) {
     string parameter=map.usage=="base"?"base_map_m_":map.usage=="detail"?"detail_map_m_":map.usage=="bump"?"bump_map_m_":null;
     if(parameter==null)throw new Exception("Unknown terrain map: "+map.usage);
     BitmapParameter(parameters,parameter+i,Safe(map.bitmap),map.scale_x,map.scale_y,map.offset_x,map.offset_y);
    }
    // Without a detail map the layer uses neutral 50% gray, so its color is the base texture's.
    if(!maps.Any(m=>m.usage=="detail"))BitmapParameter(parameters,"detail_map_m_"+i,"shaders\\default_bitmaps\\bitmaps\\gray_50_percent",1,1);
   }
   tag.Save();
  }
  using(var tag=new TagFile(path)) {
   var references=AllReferences(tag.Fields).Where(r=>r.Path!=null).Select(r=>r.Path.RelativePathWithExtension).ToArray();
   if(!references.Contains(item.blend_map+".bitmap") || layers.SelectMany(l=>l.maps).Any(m=>!references.Contains(m.bitmap+".bitmap")))throw new Exception("Generated terrain shader lost a texture.");
   return new{shader=target,references=references};
  }
 }
 static long I(TagField[] f,string name){return F<TagFieldElementInteger>(f,name).Data;}
 static IEnumerable<TagFieldReference> References(TagField[] fields) {
  foreach(var f in fields) {
   var reference=f as TagFieldReference;if(reference!=null)yield return reference;
   var structure=f as TagFieldStruct;
   if(structure!=null)foreach(var e in structure.Elements)foreach(var r in References(e.Fields))yield return r;
  }
 }
 static IEnumerable<TagFieldReference> AllReferences(TagField[] fields) {
  foreach(var field in fields) {
   var reference=field as TagFieldReference;if(reference!=null)yield return reference;
   var structure=field as TagFieldStruct;
   if(structure!=null)foreach(var e in structure.Elements)foreach(var r in AllReferences(e.Fields))yield return r;
   var block=field as TagFieldBlock;
   if(block!=null)foreach(var e in block.Elements)foreach(var r in AllReferences(e.Fields))yield return r;
  }
 }
 static string Remap(string path,string source,string target) {
  if(path.Equals(source,StringComparison.OrdinalIgnoreCase))return target;
  string oldRoot=Path.GetDirectoryName(source)+"\\",newRoot=Path.GetDirectoryName(target)+"\\";
  return path.StartsWith(oldRoot,StringComparison.OrdinalIgnoreCase)?newRoot+path.Substring(oldRoot.Length):path;
 }
 static string Digest(byte[] data) {using(var h=SHA256.Create())return Convert.ToBase64String(h.ComputeHash(data));}
 static void VerifyCopiedScenario(string source,string target,bool allowAddedScenery=false) {
  using(var original=new TagFile(TagPath.FromPathAndType(source,"scnr*")))
  using(var copy=new TagFile(TagPath.FromPathAndType(target,"scnr*"))) {
   foreach(var reference in AllReferences(copy.Fields)) {
    if(reference.Path==null)continue;
    var old=reference.Path;string normalized=Remap(old.RelativePath,target,source);
    if(normalized!=old.RelativePath)reference.Path=TagPath.FromPathAndType(normalized,old.Type);
   }
   if(allowAddedScenery) {
    foreach(string name in new[]{"scenery","scenery palette","object names"}) {
     var before=F<TagFieldBlock>(original.Fields,name);var after=F<TagFieldBlock>(copy.Fields,name);
     if(after.Elements.Count<before.Elements.Count)throw new Exception("Original "+name+" entries were removed.");
     for(int i=0;i<before.Elements.Count;i++)if(Digest(before.SerializeElement(i))!=Digest(after.SerializeElement(i)))throw new Exception("Original "+name+" entry changed: "+i);
     after.DeserializeEntireBlock(before.SerializeEntireBlock());
    }
    F<TagFieldBlock>(copy.Fields,"skies").DeserializeEntireBlock(F<TagFieldBlock>(original.Fields,"skies").SerializeEntireBlock());
   }
   // Halo's save postprocessor sorts firing positions within AI zones and
   // recomputes derived area statistics. Verify those exact point multisets,
   // tolerate only tiny derived-stat rounding, then normalize in memory only.
   var oz=original.Fields.OfType<TagFieldBlock>().Single(b=>b.FieldName=="zones");
   var cz=copy.Fields.OfType<TagFieldBlock>().Single(b=>b.FieldName=="zones");
   if(oz.Elements.Count!=cz.Elements.Count)throw new Exception("AI zone count changed.");
   for(int i=0;i<oz.Elements.Count;i++) {
    var op=F<TagFieldBlock>(oz.Elements[i].Fields,"firing positions");var cp=F<TagFieldBlock>(cz.Elements[i].Fields,"firing positions");
    var left=Enumerable.Range(0,op.Elements.Count).Select(n=>Digest(op.SerializeElement(n))).OrderBy(x=>x).ToArray();
    var right=Enumerable.Range(0,cp.Elements.Count).Select(n=>Digest(cp.SerializeElement(n))).OrderBy(x=>x).ToArray();
    if(!left.SequenceEqual(right))throw new Exception("AI firing-position data changed in zone "+i);
    cp.DeserializeEntireBlock(op.SerializeEntireBlock());
    var oa=F<TagFieldBlock>(oz.Elements[i].Fields,"areas");var ca=F<TagFieldBlock>(cz.Elements[i].Fields,"areas");
    if(oa.Elements.Count!=ca.Elements.Count)throw new Exception("AI area count changed.");
    for(int n=0;n<oa.Elements.Count;n++)foreach(var field in oa.Elements[n].Fields.Where(f=>f.FieldName.StartsWith("runtime "))) {
     var other=ca.Elements[n].Fields.Single(f=>f.FieldName==field.FieldName && f.GetType()==field.GetType());
     var number=field as TagFieldElementSingle;
     if(number!=null) {var value=(TagFieldElementSingle)other;if(Math.Abs(number.Data-value.Data)>0.0001f)throw new Exception("AI runtime statistic changed beyond rounding tolerance.");value.Data=number.Data;}
     var vector=field as TagFieldElementArraySingle;
     if(vector!=null) {var value=(TagFieldElementArraySingle)other;if(vector.Data.Length!=value.Data.Length || vector.Data.Zip(value.Data,(a,b)=>Math.Abs(a-b)).Any(d=>d>0.0001f))throw new Exception("AI runtime vector changed beyond rounding tolerance.");value.Data=vector.Data;}
    }
   }
   if(Digest(original.Serialize())!=Digest(copy.Serialize()))throw new Exception("Copied scenario data changed beyond relocated references and verified AI save normalization.");
  }
 }
 static void CopyLevel(Job j) {
  string source=Safe(j.template),target=Safe(j.scenario),root=Path.Combine(kit,"tags");
  string parent=Path.GetDirectoryName(target),leaf=Path.GetFileName(target);
  if(parent!="levels\\multi\\"+leaf || leaf.Length<3 || leaf.Length>32 || leaf.Any(c=>!(c>='a'&&c<='z')&&!(c>='0'&&c<='9')&&c!='_'))throw new Exception("Copy destination must be a new HaloBridge level namespace.");
  string srcRoot=Path.GetFullPath(Path.Combine(root,Path.GetDirectoryName(source))),dstRoot=Path.GetFullPath(Path.Combine(root,parent));
  if(!srcRoot.StartsWith(Path.GetFullPath(root)+"\\",StringComparison.OrdinalIgnoreCase) || dstRoot.StartsWith(srcRoot+"\\",StringComparison.OrdinalIgnoreCase) || srcRoot.Equals(dstRoot,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid source/destination relationship.");
  if(!File.Exists(Path.Combine(root,source+".scenario")))throw new Exception("The original editable scenario is missing. Extract the Editing Kit tag archives first: "+source);
  if(Directory.Exists(dstRoot))throw new Exception("The destination level already exists. Choose a new output level name.");
  var files=Directory.GetFiles(srcRoot,"*",SearchOption.AllDirectories);
  var hashes=new Dictionary<string,string>();var copied=new List<string>();var missing=new HashSet<string>();var bytePreserved=new List<string>();int redirected=0,verified=0;
  foreach(var file in files) {
   if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0)throw new Exception("Linked source files are not supported: "+file);
   string relative=file.Substring(root.Length+1);string sourceTag=relative.Substring(0,relative.Length-Path.GetExtension(file).Length);
   string destination=Path.Combine(root,Remap(sourceTag,source,target)+Path.GetExtension(file));
   if(!Path.GetFullPath(destination).StartsWith(dstRoot+"\\",StringComparison.OrdinalIgnoreCase))throw new Exception("Copy escaped the destination namespace.");
   hashes[file]=Digest(File.ReadAllBytes(file));Directory.CreateDirectory(Path.GetDirectoryName(destination));File.Copy(file,destination,false);copied.Add(destination);
  }
  for(int i=0;i<copied.Count;i++) {
   string file=copied[i];File.WriteAllText(j.output+".progress.json",js.Serialize(new{message="Verifying copied level tags "+(i+1)+"/"+copied.Count+": "+Path.GetFileName(file)}));
   // This installed ManagedBlam cannot enumerate RealSlider fields in camera
   // settings. Preserve these opaque tags byte-for-byte, only when no original
   // level path occurs in either supported tag-string encoding.
   if(Path.GetExtension(file)==".camera_fx_settings") {
    var bytes=File.ReadAllBytes(file);string prefix=Path.GetDirectoryName(source)+"\\";
    if(System.Text.Encoding.UTF8.GetString(bytes).IndexOf(prefix,StringComparison.OrdinalIgnoreCase)>=0 || System.Text.Encoding.Unicode.GetString(bytes).IndexOf(prefix,StringComparison.OrdinalIgnoreCase)>=0)throw new Exception("Camera settings contain level-local paths that this ManagedBlam cannot safely relocate: "+file);
    bytePreserved.Add(file.Substring(root.Length+1));continue;
   }
   // Byte-identical copies retain embedded resource streams; only referenced
   // paths inside the original level namespace are changed through ManagedBlam.
   using(var tag=new TagFile(TagPath.FromFilename(file))) {
    string before=Digest(tag.Serialize());bool changed=false;
    var changedRefs=new List<Tuple<TagFieldReference,TagPath>>();
    foreach(var reference in AllReferences(tag.Fields)) {
     if(reference.Path==null)continue;
     var old=reference.Path;string replacement=Remap(old.RelativePath,source,target);
     if(replacement==old.RelativePath)continue;
     if(!File.Exists(Path.Combine(root,replacement+Path.GetExtension(old.RelativePathWithExtension)))) {
      if(File.Exists(old.Filename))throw new Exception("A source dependency was not copied: "+old.RelativePathWithExtension);
      missing.Add(old.RelativePathWithExtension);continue; // Retain original dangling references, never invent replacement tags.
     }
     reference.Path=TagPath.FromPathAndType(replacement,old.Type);changedRefs.Add(Tuple.Create(reference,old));changed=true;redirected++;
    }
    if(changed)tag.Save();
    foreach(var pair in changedRefs)pair.Item1.Path=pair.Item2;
    if(Digest(tag.Serialize())!=before)throw new Exception("Tag data changed beyond reference relocation: "+file);
    verified++;
   }
  }
  foreach(var pair in hashes)if(Digest(File.ReadAllBytes(pair.Key))!=pair.Value)throw new Exception("Original tags changed while copying. Retry after closing other tag editors.");
  VerifyCopiedScenario(source,target);
  using(var original=new TagFile(TagPath.FromPathAndType(source,"scnr*")))
  using(var copy=new TagFile(TagPath.FromPathAndType(target,"scnr*"))) {
   var counts=original.Fields.OfType<TagFieldBlock>().ToDictionary(b=>b.FieldName,b=>b.Elements.Count);
   foreach(var b in copy.Fields.OfType<TagFieldBlock>())if(counts[b.FieldName]!=b.Elements.Count)throw new Exception("Scenario block count changed: "+b.FieldName);
   File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,scenario=target,source=source,copied_files=copied.Count,verified_tags=verified,byte_preserved_camera_settings=bytePreserved,redirected_references=redirected,scenario_blocks=counts,originals_unchanged=true,missing_original_references=missing.ToArray(),shared_assets="Tags outside the source level folder remain shared references."}));
  }
 }
 static void ResolveScenery(Job j) {
  var wanted=new HashSet<string>((j.sources??new string[0]).Select(Safe),StringComparer.OrdinalIgnoreCase);
  var matches=new List<object>();var errors=new List<string>();string root=Path.Combine(kit,"tags");
  foreach(string file in Directory.EnumerateFiles(root,"*.scenery",SearchOption.AllDirectories)) {
   string source=file.Substring(root.Length+1);source=source.Substring(0,source.Length-8);
   try {
    using(var scenery=new TagFile(TagPath.FromPathAndType(source,"scen*"))) {
     var modelRef=References(scenery.Fields).FirstOrDefault(r=>r.FieldName=="model" && r.Path!=null);
     if(modelRef==null)continue;
     using(var model=new TagFile(TagPath.FromPathAndType(modelRef.Path.RelativePath,"hlmt*"))) {
      var refs=References(model.Fields).ToArray();
      var render=refs.FirstOrDefault(r=>r.FieldName=="render model" && r.Path!=null);
      if(render==null || !wanted.Contains(render.Path.RelativePath))continue;
      var collision=refs.FirstOrDefault(r=>r.FieldName=="collision model" && r.Path!=null);
      if(collision==null || !File.Exists(Path.Combine(root,collision.Path.RelativePath+".collision_model")))continue;
      matches.Add(new {render=render.Path.RelativePath,scenery=source,model=modelRef.Path.RelativePath,collision=collision.Path.RelativePath});
     }
    }
   }catch(Exception e){errors.Add(source+": "+e.Message);}
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,matches=matches,warnings=errors}));
 }
 // Diagnostic: non-empty field values of tags (sources = "path.extension"), for comparing with Bungie's tags.
 static void DumpTags(Job j) {
  var result=new Dictionary<string,List<string>>();
  foreach(var source in j.sources??new string[0]) {
   var lines=new List<string>();int bar=source.LastIndexOf('|');
   using(var tag=new TagFile(TagPath.FromPathAndType(Safe(source.Substring(0,bar)),source.Substring(bar+1))))Dump(tag.Fields,"",lines,0);
   result[source]=lines;
  }
  File.WriteAllText(j.output,js.Serialize(result));
 }
 static void Dump(TagField[] fields,string prefix,List<string> lines,int depth) {
  if(depth>6||lines.Count>4000)return;
  foreach(var f in fields) {
   string name=prefix+f.FieldName;
   var st=f as TagFieldStruct;if(st!=null){foreach(var e in st.Elements)Dump(e.Fields,name+"/",lines,depth+1);continue;}
   var bl=f as TagFieldBlock;if(bl!=null){if(bl.Elements.Count>0)lines.Add(name+" ["+bl.Elements.Count+"]");for(int i=0;i<Math.Min(bl.Elements.Count,12);i++)Dump(bl.Elements[i].Fields,name+"["+i+"]/",lines,depth+1);continue;}
   string value=null;
   var r=f as TagFieldReference;if(r!=null)value=r.Path==null?null:r.Path.RelativePathWithExtension;
   var en=f as TagFieldEnum;if(en!=null)value=en.Value.ToString();
   var ei=f as TagFieldElementInteger;if(ei!=null)value=ei.Data.ToString();
   var es=f as TagFieldElementSingle;if(es!=null)value=es.Data.ToString();
   var ea=f as TagFieldElementArraySingle;if(ea!=null)value=String.Join(",",ea.Data);
   var sid=f as TagFieldElementStringID;if(sid!=null)value=sid.Data;
   var sn=f as TagFieldElementStringNormal;if(sn!=null)value=sn.Data;
   var bi=f as TagFieldBlockIndex;if(bi!=null)value=bi.Value.ToString();
   if(!String.IsNullOrEmpty(value)&&value!="0"&&value!="-1"&&value!="0,0,0")lines.Add(name+" = "+value);
  }
 }
 // A sky converted from another game: the render model Tool built with render-sky gets a
 // model and a scenery tag (as Bungie's skies have), and the scenario's skies use it.
 static void SkyObject(Job j) {
  string level=Path.GetDirectoryName(Safe(j.scenario))+"\\";string target=Safe(j.template);
  if(!target.StartsWith(level,StringComparison.OrdinalIgnoreCase))throw new Exception("The converted sky is outside this level.");
  if(!File.Exists(Path.Combine(kit,"tags",target+".render_model")))throw new Exception("Tool did not build the sky render model: "+target);
  // The sky's own sun and sky light (from a Halo 2 sky), which lightmaps use as Bungie's skies' 200 sky lights.
  int lightCount=0;
  if(j.sky_lights!=null && j.sky_lights.Length>0) {
   if(j.sky_lights.Length>200)throw new Exception("A sky has at most 200 sky lights.");
   foreach(var light in j.sky_lights)if(light.direction==null||light.direction.Length!=3||light.intensity==null||light.intensity.Length!=3||!(light.solid_angle>0)||light.direction.Concat(light.intensity).Any(x=>float.IsNaN(x)||float.IsInfinity(x)||x<-1e7||x>1e7))throw new Exception("Invalid sky light");
   using(var render=new TagFile(TagPath.FromPathAndType(target,"mode"))) {
    var block=F<TagFieldBlock>(render.Fields,"sky lights");
    while(block.Elements.Count>0)block.RemoveElement(block.Elements.Count-1);
    foreach(var light in j.sky_lights) {
     var f=block.AddElement().Fields;
     F<TagFieldElementArraySingle>(f,"direction").Data=light.direction;
     F<TagFieldElementArraySingle>(f,"intensity").Data=light.intensity;
     F<TagFieldElementSingle>(f,"solid angle").Data=light.solid_angle;
    }
    render.Save();
    lightCount=block.Elements.Count;
   }
  }
  using(var model=new TagFile()) {
   var path=TagPath.FromPathAndType(target,"hlmt");
   if(File.Exists(Path.Combine(kit,"tags",target+".model")))model.Load(path);else model.New(path);
   F<TagFieldReference>(model.Fields,"render model").Path=TagPath.FromPathAndType(target,"mode");
   model.Save();
  }
  using(var scenery=new TagFile()) {
   var path=TagPath.FromPathAndType(target,"scen");
   if(File.Exists(Path.Combine(kit,"tags",target+".scenery")))scenery.Load(path);else scenery.New(path);
   var obj=S(scenery.Fields,"object");
   F<TagFieldReference>(obj,"model").Path=TagPath.FromPathAndType(target,"hlmt");
   if(j.radius>0)F<TagFieldElementSingle>(obj,"bounding radius").Data=j.radius;
   scenery.Save();
  }
  using(var tag=new TagFile(TagPath.FromPathAndType(Safe(j.scenario),"scnr*"))) {
   var skies=F<TagFieldBlock>(tag.Fields,"skies");
   if(skies.Elements.Count==0)skies.AddElement();
   // Keep existing slots so every BSP's sky index stays valid.
   foreach(var element in skies.Elements)F<TagFieldReference>(element.Fields,"sky").Path=TagPath.FromPathAndType(target,"scen");
   tag.Save();
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,sky=target+".scenery",sky_lights=lightCount}));
 }
 // Tool gives every instanced geometry piece per-vertex lighting: the bake stores light only at
 // triangle corners, which smears it across large, low-detail triangles (Halo 2 terrain) and
 // leaves hard steps where pieces meet. Pieces at least j.radius world units across (bounding
 // sphere radius) get per-pixel lighting ("per-pixel shared", 3; Tool refuses "per-pixel seperate") instead; small ones keep
 // per-vertex, which suits them and keeps the lightmap page for the large surfaces.
 // The original map's player starting locations replace the scenario's (Halo 3 and ODST name the
 // BSP or insertion point index differently; fields a game lacks are skipped), and its kill trigger
 // volumes become Halo 3 trigger volumes listed as kill triggers.
 static TagField Opt(TagField[] fields,string name){return fields.FirstOrDefault(f=>f.FieldName==name);}
 static void SetFloats(TagField[] fields,string name,float[] values) {
  var f=Opt(fields,name) as TagFieldElementArraySingle;if(f==null||values==null)return;
  var data=f.Data;for(int i=0;i<data.Length && i<values.Length;i++)data[i]=values[i];f.Data=data;
 }
 static void Gameplay(TagFile tag,Job j) {
  var result=new Dictionary<string,object>();
  if(j.starts!=null && j.starts.Length>0) {
   var starts=F<TagFieldBlock>(tag.Fields,"player starting locations");
   while(starts.Elements.Count>0)starts.RemoveElement(starts.Elements.Count-1);
   foreach(var s in j.starts) {
    if(s.position==null||s.position.Length!=3||s.position.Any(x=>Single.IsNaN(x)||Single.IsInfinity(x)))continue;
    var fields=starts.AddElement().Fields;
    SetFloats(fields,"position",s.position);
    var facing=Opt(fields,"facing");
    if(facing is TagFieldElementArraySingle)SetFloats(fields,"facing",new[]{s.facing,0f});
    else if(facing is TagFieldElementSingle)((TagFieldElementSingle)facing).Data=s.facing;
    foreach(var name in new[]{"bsp index","insertion point index"}){var index=Opt(fields,name) as TagFieldElementInteger;if(index!=null)index.Data=0;}
   }
   result["starts"]=starts.Elements.Count;
  }
  if(j.kill_volumes!=null && j.kill_volumes.Length>0) {
   var volumes=F<TagFieldBlock>(tag.Fields,"trigger volumes");
   int added=0;
   foreach(var k in j.kill_volumes) {
    string name=(k.name??"").Length>0?k.name:"kill_"+added;
    // Replace a volume of the same name (prepared again) instead of adding a copy.
    int index=-1;
    for(int i=0;i<volumes.Elements.Count;i++){var n=Opt(volumes.Elements[i].Fields,"name") as TagFieldElementStringID;if(n!=null && n.Data==name)index=i;}
    if(index<0){index=volumes.Elements.Count;volumes.AddElement();}
    var fields=volumes.Elements[index].Fields;
    var nf=Opt(fields,"name") as TagFieldElementStringID;if(nf!=null)nf.Data=name;
    SetFloats(fields,"forward",k.forward);SetFloats(fields,"up",k.up);SetFloats(fields,"position",k.position);SetFloats(fields,"extents",k.extents);
    // "C" is the box's half diagonal (Guardian: extents 98.1 x 111.4 x 14.5 -> 74.6).
    var c=Opt(fields,"C") as TagFieldElementSingle;
    if(c!=null && k.extents!=null && k.extents.Length==3)c.Data=(float)(Math.Sqrt(k.extents[0]*k.extents[0]+k.extents[1]*k.extents[1]+k.extents[2]*k.extents[2])/2);
    // A trigger volume is a kill volume when its "kill trigger volume" is set: Bungie's Narrows
    // marks kill_drop 0 and its other volumes -1, and the "scenario kill triggers" block stays
    // empty in the tag (it is built when the map is compiled).
    var back=Opt(fields,"kill trigger volume") as TagFieldBlockIndex;if(back!=null)back.Value=added;
    added++;
   }
   result["kill_volumes"]=added;
  }
  if(j.netgame!=null)result["netgame"]=Netgame(tag,j.netgame,Path.GetDirectoryName(Safe(j.scenario)));
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,gameplay=result}));
 }
 // Multiplayer objects as crates named hb_ng_<n>: updated in place when prepared again; ones no
 // longer wanted are removed (their names unlinked), and every crate's name link is reconciled.
 // A level copy of a multiplayer crate with no model and no effects: a converted level shows its
 // own teleporter (Halo 2's teleporter scenery, Halo CE's pads), so Halo 3's model and glow would
 // sit on top of it. The copy keeps the crate's gameplay (teleporting, its boundary) and sounds.
 static string BareCrate(string level,string source,Dictionary<string,string> made) {
  string done;if(made.TryGetValue(source,out done))return done;
  string target=level+"\\objects\\"+source.Substring(source.LastIndexOf('\\')+1)+"_bare";
  string from=Path.Combine(kit,"tags",source+".crate"),to=Path.Combine(kit,"tags",target+".crate");
  if(!File.Exists(from))return source;
  Directory.CreateDirectory(Path.GetDirectoryName(to));File.Copy(from,to,true);
  using(var t=new TagFile(TagPath.FromPathAndType(target,"bloc"))) {
   var obj=S(t.Fields,"object");
   F<TagFieldReference>(obj,"model").Path=null;
   var radius=F<TagFieldElementSingle>(obj,"bounding radius");if(radius.Data<1)radius.Data=1;
   var attachments=F<TagFieldBlock>(obj,"attachments");
   for(int i=attachments.Elements.Count-1;i>=0;i--){var r=F<TagFieldReference>(attachments.Elements[i].Fields,"type").Path;if(r==null||!r.RelativePathWithExtension.EndsWith(".sound_looping",StringComparison.OrdinalIgnoreCase))attachments.RemoveElement(i);}
   t.Save();
  }
  made[source]=target;return target;
 }
 static int Netgame(TagFile tag,NetObject[] objects,string level) {
  var made=new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
  foreach(var o in objects)if(o.bare && !String.IsNullOrEmpty(o.tag))o.tag=BareCrate(level,Safe(o.tag),made);
  var crates=F<TagFieldBlock>(tag.Fields,"crates");var palette=F<TagFieldBlock>(tag.Fields,"crate palette");var names=F<TagFieldBlock>(tag.Fields,"object names");
  Func<int,string> crateName=i=>{int ni=F<TagFieldBlockIndex>(crates.Elements[i].Fields,"name").Value;return ni>=0 && ni<names.Elements.Count?F<TagFieldElementStringNormal>(names.Elements[ni].Fields,"name").Data:"";};
  var valid=objects.Where(o=>o.position!=null && o.position.Length==3 && !o.position.Any(x=>Single.IsNaN(x)||Single.IsInfinity(x)) && File.Exists(Path.Combine(kit,"tags",Safe(o.tag)+".crate"))).ToArray();
  var wanted=new HashSet<string>(Enumerable.Range(0,valid.Length).Select(i=>"hb_ng_"+i));
  for(int i=crates.Elements.Count-1;i>=0;i--){string n=crateName(i);if(n.StartsWith("hb_ng_") && !wanted.Contains(n)){int ni=F<TagFieldBlockIndex>(crates.Elements[i].Fields,"name").Value;crates.RemoveElement(i);if(ni>=0)F<TagFieldBlockIndex>(names.Elements[ni].Fields,"scenario_datum_index").Value=-1;}}
  for(int k=0;k<valid.Length;k++) {
   var o=valid[k];string name="hb_ng_"+k;
   int pi=-1;for(int i=0;i<palette.Elements.Count;i++){var r=F<TagFieldReference>(palette.Elements[i].Fields,"name").Path;if(r!=null && r.RelativePath.Equals(o.tag,StringComparison.OrdinalIgnoreCase))pi=i;}
   if(pi<0){pi=palette.Elements.Count;F<TagFieldReference>(palette.AddElement().Fields,"name").Path=TagPath.FromPathAndType(Safe(o.tag),"bloc*");}
   int ci=-1;for(int i=0;i<crates.Elements.Count;i++)if(crateName(i)==name)ci=i;
   TagField[] f;
   if(ci>=0)f=crates.Elements[ci].Fields;
   else {
    ci=crates.Elements.Count;f=crates.AddElement().Fields;
    int ni=-1;for(int i=0;i<names.Elements.Count;i++)if(F<TagFieldElementStringNormal>(names.Elements[i].Fields,"name").Data==name)ni=i;
    if(ni<0){ni=names.Elements.Count;F<TagFieldElementStringNormal>(names.AddElement().Fields,"name").Data=name;}
    var nf=names.Elements[ni].Fields;F<TagFieldBlockIndex>(nf,"object_type").Value=10;F<TagFieldBlockIndex>(f,"name").Value=ni;
    var oid=S(S(f,"object data"),"object id");F<TagFieldElementInteger>(oid,"unique id").Data=0x48420000+k;F<TagFieldEnum>(oid,"type").Value=10;F<TagFieldEnum>(oid,"source").Value=1;F<TagFieldBlockIndex>(oid,"origin bsp index").Value=-1;
   }
   F<TagFieldBlockIndex>(f,"type").Value=pi;
   var data=S(f,"object data");F<TagFieldElementArraySingle>(data,"position").Data=o.position;F<TagFieldElementArraySingle>(data,"rotation").Data=new[]{o.yaw,0f,0f};F<TagFieldElementSingle>(data,"scale").Data=1f;
   var mp=S(f,"multiplayer data");
   var team=Opt(mp,"owner team") as TagFieldEnum;if(team!=null)team.Value=o.team;
   var channel=Opt(mp,"teleporter channel") as TagFieldEnum;if(channel!=null)channel.Value=Math.Max(0,Math.Min(o.channel,9));
   var shape=Opt(mp,"boundary shape") as TagFieldEnum;if(shape!=null)shape.Value=o.shape;
   if(o.shape>0) {
    foreach(var pair in new[]{Tuple.Create("boundary width or radius",o.radius),Tuple.Create("boundary box length",o.radius*2),Tuple.Create("boundary positive height",o.height),Tuple.Create("boundary negative height",1f)}){var v=Opt(mp,pair.Item1) as TagFieldElementSingle;if(v!=null)v.Data=pair.Item2;}
   }
  }
  for(int i=0;i<crates.Elements.Count;i++){int ni=F<TagFieldBlockIndex>(crates.Elements[i].Fields,"name").Value;if(ni>=0 && ni<names.Elements.Count)F<TagFieldBlockIndex>(names.Elements[ni].Fields,"scenario_datum_index").Value=i;}
  return valid.Length;
 }
 static void LightmapPolicy(Job j) {
  string level=Path.GetDirectoryName(Safe(j.scenario));string bsp=Safe(j.scenario);
  int changed=0,total=0,reports=0;
  using(var tag=new TagFile(TagPath.FromPathAndType(bsp,"sbsp"))) {
   foreach(var element in F<TagFieldBlock>(tag.Fields,"instanced geometry instances").Elements) {
    total++;
    var policy=F<TagFieldEnum>(element.Fields,"lightmapping policy");
    if(F<TagFieldElementSingle>(element.Fields,"world bounding sphere radius").Data>=j.radius && policy.Value==1){policy.Value=3;changed++;}
   }
   // Tool's warning reports (red "overlapping surfaces" markers in Sapien). The game does not use
   // them; HaloBridge's preparation report lists the same warnings. Kept when asked for.
   if(j.template!="keep_markers") {
    var errors=F<TagFieldBlock>(tag.Fields,"errors");reports=errors.Elements.Count;
    while(errors.Elements.Count>0)errors.RemoveElement(errors.Elements.Count-1);
   }
   if(changed>0||reports>0)tag.Save();
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,instances=total,per_pixel=changed,cleared_reports=reports}));
 }
 // The level's lightmap geometry after Tool's faux_data_sync / faux_farm_finish: every mesh's raw
 // vertices (position, normal, texcoord, lightmap texcoord) and triangle indices, as CSV for the
 // Halo 2 lightmap transfer. Only per-pixel meshes have lightmap texcoords.
 static void LightmapMesh(Job j) {
  string level=Safe(j.scenario);
  int meshCount=0;
  using(var tag=new TagFile(TagPath.FromPathAndType(level,"Lbsp")))
  using(var w=new StreamWriter(j.sources[0])) {
   w.WriteLine("path,mesh,vertex,px,py,pz,nx,ny,nz,u,v,lu,lv");
   var inv=System.Globalization.CultureInfo.InvariantCulture;
   var geometry=S(tag.Fields,"imported geometry");
   var meshes=F<TagFieldBlock>(geometry,"per mesh temporary");
   for(int m=0;m<meshes.Elements.Count;m++) {
    var fields=meshes.Elements[m].Fields;
    var raw=F<TagFieldBlock>(fields,"raw vertices");
    for(int i=0;i<raw.Elements.Count;i++) {
     var v=raw.Elements[i].Fields;
     Func<string,float[]> A=n=>F<TagFieldElementArraySingle>(v,n).Data;
     var values=A("position").Concat(A("normal")).Concat(A("texcoord").Take(2)).Concat(A("lightmap texcoord").Take(2));
     w.WriteLine("imported geometry/,"+m+","+i+","+string.Join(",",values.Select(x=>x.ToString("R",inv))));
    }
    var idx=F<TagFieldBlock>(fields,"raw indices");
    w.WriteLine("#indices,imported geometry/,"+m+","+string.Join(" ",idx.Elements.Select(e=>((TagFieldElementInteger)e.Fields.First(x=>x is TagFieldElementInteger)).Data)));
   }
   meshCount=meshes.Elements.Count;
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,meshes=meshCount}));
 }
 // Instances lit per vertex: each instance's definition mesh (an index into the lightmap BSP's
 // imported geometry, whose raw vertices are in the definition's own space), its placement and
 // its block of per-vertex light ("bsp per-vertex data": one lightprobe entry per raw vertex).
 static void PervertexRead(Job j) {
  string level=Safe(j.scenario);
  var items=new List<object>();
  using(var bsp=new TagFile(TagPath.FromPathAndType(level,"sbsp")))
  using(var lbsp=new TagFile(TagPath.FromPathAndType(level,"Lbsp"))) {
   var resource=S(bsp.Fields,"resource interface");
   var rawItems=S(F<TagFieldBlock>(resource,"raw_resources").Elements[0].Fields,"raw_items");
   var definitions=F<TagFieldBlock>(rawItems,"instanced geometries definitions");
   var instances=F<TagFieldBlock>(bsp.Fields,"instanced geometry instances");
   var lights=F<TagFieldBlock>(lbsp.Fields,"instances");
   var blocks=F<TagFieldBlock>(lbsp.Fields,"bsp per-vertex data");
   // Definition meshes store positions compressed to 0..1 inside these bounds
   // (bounds 0 = x min, x max, y min; bounds 1 = y max, z min, z max).
   var compression=F<TagFieldBlock>(S(bsp.Fields,"render geometry"),"compression info");
   for(int i=0;i<instances.Elements.Count && i<lights.Elements.Count;i++) {
    var f=instances.Elements[i].Fields;
    int block=(int)F<TagFieldElementInteger>(lights.Elements[i].Fields,"pervertex block index").Data;
    int definition=F<TagFieldBlockIndex>(f,"instance definition").Value;
    if(block<0||block>=blocks.Elements.Count||definition<0||definition>=definitions.Elements.Count)continue;
    int mesh=(int)F<TagFieldElementInteger>(definitions.Elements[definition].Fields,"mesh index").Data;
    int count=F<TagFieldBlock>(blocks.Elements[block].Fields,"lightprobe data").Elements.Count;
    int ci=(int)F<TagFieldElementInteger>(definitions.Elements[definition].Fields,"compression index").Data;
    float[] bounds=null;
    if(ci>=0 && ci<compression.Elements.Count){var c=compression.Elements[ci].Fields;bounds=F<TagFieldElementArraySingle>(c,"position bounds 0").Data.Concat(F<TagFieldElementArraySingle>(c,"position bounds 1").Data).ToArray();}
    items.Add(new{instance=i,mesh=mesh,block=block,count=count,bounds=bounds,scale=F<TagFieldElementSingle>(f,"scale").Data,
     forward=F<TagFieldElementArraySingle>(f,"forward").Data,left=F<TagFieldElementArraySingle>(f,"left").Data,
     up=F<TagFieldElementArraySingle>(f,"up").Data,position=F<TagFieldElementArraySingle>(f,"position").Data});
   }
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,instances=items}));
 }
 // Per-vertex light from j.sources[1] (little-endian float32): for each block listed in j.sources[0]
 // (JSON [[block,count],...], in order), count x 15 values per vertex: dominant light intensity
 // r,g,b, then the red, green and blue linear SH terms (4 each). A vertex whose first value is NaN
 // keeps Tool's light. Stored as half floats, as Tool writes them.
 static void PervertexWrite(Job j) {
  string level=Safe(j.scenario);
  var order=js.Deserialize<int[][]>(File.ReadAllText(j.sources[0]));
  var data=File.ReadAllBytes(j.sources[1]);int at=0,written=0;
  Func<float> next=()=>{float v=BitConverter.ToSingle(data,at);at+=4;return v;};
  using(var lbsp=new TagFile(TagPath.FromPathAndType(level,"Lbsp"))) {
   var blocks=F<TagFieldBlock>(lbsp.Fields,"bsp per-vertex data");
   string[] colors={"red lightprobe terms","green lightprobe terms","blue lightprobe terms"};
   foreach(var entry in order) {
    var probes=F<TagFieldBlock>(blocks.Elements[entry[0]].Fields,"lightprobe data");
    if(probes.Elements.Count!=entry[1])throw new Exception("Per-vertex block "+entry[0]+" has "+probes.Elements.Count+" vertices, not "+entry[1]);
    for(int v=0;v<entry[1];v++) {
     var values=new float[15];for(int k=0;k<15;k++)values[k]=next();
     if(float.IsNaN(values[0]))continue;
     var p=probes.Elements[v].Fields;
     F<TagFieldElementInteger>(p,"dominant light intensity r").Data=Half(values[0]);
     F<TagFieldElementInteger>(p,"dominant light intensity g").Data=Half(values[1]);
     F<TagFieldElementInteger>(p,"dominant light intensity b").Data=Half(values[2]);
     for(int c=0;c<3;c++){var terms=F<TagFieldArray>(p,colors[c]);for(int t=0;t<4;t++)F<TagFieldElementInteger>(terms.Elements[t].Fields,"coefficient").Data=Half(values[3+c*4+t]);}
     written++;
    }
   }
   if(at!=data.Length)throw new Exception("Per-vertex light data has "+data.Length+" bytes; the blocks use "+at);
   lbsp.Save();
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,vertices=written}));
 }
 // A float as IEEE half-float bits in a signed 16-bit value (how the tag stores it).
 static short Half(float value) {
  uint b=BitConverter.ToUInt32(BitConverter.GetBytes(value),0);
  uint sign=(b>>16)&0x8000;int exp=(int)((b>>23)&0xff)-127+15;uint mant=b&0x7fffff;
  uint h;
  if(exp<=0){h=exp<-10?0:((mant|0x800000)>>(13-exp));h=(h+1)>>1;}  // subnormal, rounded
  else if(exp>=31)h=0x7bff;  // clamp to the largest finite half
  else{h=(uint)(exp<<10)|(mant>>13);if((mant&0x1000)!=0)h++;}
  return unchecked((short)(sign|h));
 }
 // Replace the level's lightmap master (the 16f lp_array bitmap Tool's faux_farm_finish writes:
 // 9 layers of half-float SH coefficients) with j.sources[0]'s bytes, which must be the same size.
 static void LightmapWrite(Job j) {
  string scenario=Safe(j.scenario);string name=Path.GetFileName(scenario);
  string target=Path.GetDirectoryName(scenario)+"\\"+name+"_lightmap_"+name+"_16f_lp_array";
  if(j.template=="read") {
   // Read the master instead: its bytes go to j.sources[0].
   using(var tag=new TagFile(TagPath.FromPathAndType(target,"bitm"))) {
    var bytesOut=tag.Fields.OfType<TagFieldData>().Single(x=>x.FieldName=="processed pixel data").GetData();
    File.WriteAllBytes(j.sources[0],bytesOut);
    File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,bitmap=target,bytes=bytesOut.Length}));
   }
   return;
  }
  var bytes=File.ReadAllBytes(j.sources[0]);
  using(var tag=new TagFile(TagPath.FromPathAndType(target,"bitm"))) {
   var data=tag.Fields.OfType<TagFieldData>().Single(x=>x.FieldName=="processed pixel data");
   int size=data.GetData().Length;
   if(bytes.Length!=size)throw new Exception("The lightmap master is "+size+" bytes; the Halo 2 lightmap transfer wrote "+bytes.Length+". Tool's lighting steps must stop after faux_farm_finish.");
   data.SetData(bytes);tag.Save();
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,ok=true,bitmap=target,bytes=bytes.Length}));
 }
 static void ListSkies(Job j) {
  var items=new List<object>();var warnings=new List<string>();string root=Path.Combine(kit,"tags");
  foreach(var file in Directory.EnumerateFiles(Path.Combine(root,"levels"),"*.scenario",SearchOption.AllDirectories).OrderBy(x=>x)) {
   string scenario=file.Substring(root.Length+1);scenario=scenario.Substring(0,scenario.Length-9);
   try {using(var tag=new TagFile(TagPath.FromPathAndType(scenario,"scnr*"))) {
    var skies=F<TagFieldBlock>(tag.Fields,"skies");var refs=AllReferences(skies.Elements.Cast<TagElement>().SelectMany(e=>e.Fields).ToArray()).Where(x=>x.Path!=null).Select(x=>x.Path.RelativePathWithExtension).ToArray();
    if(refs.Length>0 && refs.All(x=>File.Exists(Path.Combine(root,x))))items.Add(new{scenario=scenario,name=Path.GetFileName(scenario),skies=refs});
   }}catch(Exception e){warnings.Add(scenario+": "+e.Message);}
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,items=items,warnings=warnings}));
 }
 static void RecoverSource(Job j) {
  using(var tag=new TagFile(TagPath.FromPathAndType(Safe(j.scenario),"sbsp*"))) {
   var stream=TagAlternateStreamType.TagImportInformation;
   if(!tag.DoesAlternateStreamExist(stream))throw new Exception("This BSP has no embedded source geometry. Original source files are required to rebuild it.");
   var fields=((TagElement)tag.GetAlternateStream(stream)).Fields;
   var files=F<TagFieldBlock>(fields,"files");var items=new List<object>();
   string folder=Path.GetDirectoryName(Path.GetFullPath(j.output));
   Directory.CreateDirectory(folder);
   for(int i=0;i<files.Elements.Count;i++) {
    var f=files.Elements[i].Fields;string name=F<TagFieldElementLongString>(f,"path").Data;
    if(!name.EndsWith(".ass",StringComparison.OrdinalIgnoreCase))continue;
    byte[] zipped=F<TagFieldData>(f,"zipped data").GetData();
    string compressed="source-"+i+".zlib";
    // Never use embedded absolute/relative source names as output paths.
    using(var output=new FileStream(Path.Combine(folder,compressed),FileMode.CreateNew,FileAccess.Write))output.Write(zipped,0,zipped.Length);
    items.Add(new{source_path=name,compressed=compressed,size=I(f,"size"),crc32=unchecked((uint)I(f,"checksum"))});
   }
   if(items.Count==0)throw new Exception("This BSP contains no recoverable ASS source geometry.");
   var shaders=AllReferences(tag.Fields).Where(r=>r.Path!=null && r.Path.Extension.StartsWith("shader",StringComparison.OrdinalIgnoreCase)).Select(r=>r.Path.RelativePath).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
   File.WriteAllText(j.output,js.Serialize(new{version=1,source=j.scenario,files=items,shaders=shaders}));
  }
 }
 static void InspectBsp(Job j) {
  using(var tag=new TagFile(TagPath.FromPathAndType(Safe(j.scenario),"sbsp*"))) {
   var block=F<TagFieldBlock>(tag.Fields,"instanced geometry instances");var items=new List<object>();
   foreach(var e in block.Elements)items.Add(new{name=F<TagFieldElementStringID>(e.Fields,"name").Data,position=F<TagFieldElementArraySingle>(e.Fields,"position").Data,scale=F<TagFieldElementSingle>(e.Fields,"scale").Data,definition=F<TagFieldBlockIndex>(e.Fields,"instance definition").Value,vectors=e.Fields.OfType<TagFieldElementArraySingle>().ToDictionary(f=>f.FieldName,f=>f.Data)});
   var resources=F<TagFieldBlock>(S(tag.Fields,"resource interface"),"raw_resources");var defs=new List<object>();
   foreach(var r in resources.Elements)foreach(var d in F<TagFieldBlock>(S(r.Fields,"raw_items"),"instanced geometries definitions").Elements) {var c=S(d.Fields,"collision info");defs.Add(new{mesh_index=I(d.Fields,"mesh index"),vertices=F<TagFieldBlock>(c,"vertices").Elements.Count,surfaces=F<TagFieldBlock>(c,"surfaces").Elements.Count});}
   File.WriteAllText(j.output,js.Serialize(new{version=1,instances=items,definitions=defs}));
  }
 }
 static object CollisionFaces(TagField[] c) {
  var vertices=F<TagFieldBlock>(c,"vertices");var edges=F<TagFieldBlock>(c,"edges");var surfaces=F<TagFieldBlock>(c,"surfaces");
     var points=vertices.Elements.Cast<TagElement>().Select(e=>F<TagFieldElementArraySingle>(e.Fields,"point").Data).ToArray();var faces=new List<int[]>();
     for(int si=0;si<surfaces.Elements.Count;si++) {
      var face=new List<int>();int first=(int)I(surfaces.Elements[si].Fields,"first edge"),edge=first;
      do {if(edge<0||edge>=edges.Elements.Count||face.Count>edges.Elements.Count)throw new Exception("Invalid collision edge loop");var f=edges.Elements[edge].Fields;bool left=I(f,"left surface")==si;face.Add((int)I(f,left?"start vertex":"end vertex"));edge=(int)I(f,left?"forward edge":"reverse edge");}while(edge!=first);
      if(face.Count>=3)faces.Add(face.ToArray());
     }
  return new{positions=points,faces=faces};
 }
 static void ModelCollision(Job j) {
  string source=Safe(j.scenario);
  // Scenario imports name the model tag directly; its render model may live elsewhere.
  string expectedRender=String.IsNullOrEmpty(j.template)?source:Safe(j.template);
  using(var model=new TagFile(TagPath.FromPathAndType(source,"hlmt*"))) {
   var refs=References(model.Fields).ToArray();
   var render=refs.Single(x=>x.FieldName=="render model").Path;
   var coll=refs.Single(x=>x.FieldName=="collision model").Path;
   if(render==null || !render.RelativePath.Equals(expectedRender,StringComparison.OrdinalIgnoreCase) || coll==null)throw new Exception("No matching collision reference for "+source);
   using(var geom=new TagFile(render))
   using(var tag=new TagFile(coll)){
    var nodes=F<TagFieldBlock>(geom.Fields,"nodes").Elements.Cast<TagElement>().ToDictionary(n=>F<TagFieldElementStringID>(n.Fields,"name").Data);
    var skeleton=F<TagFieldBlock>(geom.Fields,"nodes").Elements.Cast<TagElement>().Select(n=>new{name=F<TagFieldElementStringID>(n.Fields,"name").Data,parent=F<TagFieldBlockIndex>(n.Fields,"parent node").Value,translation=F<TagFieldElementArraySingle>(n.Fields,"default translation").Data,rotation=F<TagFieldElementArraySingle>(n.Fields,"default rotation").Data}).ToArray();
    var cnodes=F<TagFieldBlock>(tag.Fields,"nodes");
    var meshes=new List<object>();
    foreach(var region in F<TagFieldBlock>(tag.Fields,"regions").Elements)
    foreach(var perm in F<TagFieldBlock>(region.Fields,"permutations").Elements)
    foreach(var part in F<TagFieldBlock>(perm.Fields,"bsps").Elements){
     int index=(int)I(part.Fields,"node index");
     var n=nodes[F<TagFieldElementStringID>(cnodes.Elements[index].Fields,"name").Data].Fields;
     meshes.Add(new{region=F<TagFieldElementStringID>(region.Fields,"name").Data,permutation=F<TagFieldElementStringID>(perm.Fields,"name").Data,node=F<TagFieldElementStringID>(n,"name").Data,geometry=CollisionFaces(S(part.Fields,"bsp"))});
    }
    File.WriteAllText(j.output,js.Serialize(new{source=source,collision=coll.RelativePath,skeleton=skeleton,meshes=meshes}));
   }
  }
 }
 // ---- Editing Kit scenario import -------------------------------------
 // Reads the level directly from its .scenario tag: BSP and render-model
 // authoring sources (tag import info), object palettes and placements.
 // Nothing is written to the kit; blobs go to the job's own output folder.
 static TagFieldBlock Block(TagField[] fields,string name){return fields.OfType<TagFieldBlock>().FirstOrDefault(b=>b.FieldName==name);}
 static string FindStringId(TagField[] fields,string name) {
  foreach(var field in fields) {
   var value=field as TagFieldElementStringID;
   if(value!=null && value.FieldName==name)return value.Data;
   var structure=field as TagFieldStruct;
   if(structure!=null)foreach(var e in structure.Elements){string found=FindStringId(e.Fields,name);if(found!=null)return found;}
  }
  return null;
 }
 static List<object> NameTree(TagFieldBlock block,int depth) {
  var items=new List<object>();
  if(block==null || depth>3)return items;
  foreach(var e in block.Elements) {
   string name=e.Fields.OfType<TagFieldElementStringID>().Select(s=>s.Data).FirstOrDefault();
   var children=new Dictionary<string,object>();
   foreach(var child in e.Fields.OfType<TagFieldBlock>())children[child.FieldName]=NameTree(child,depth+1);
   items.Add(new{name=name??"",blocks=children});
  }
  return items;
 }
 static string[] ShaderPaths(TagFile tag) {
  // Walk only the material blocks: large BSPs have hundreds of thousands of collision elements.
  var blocks=new[]{"materials","collision materials"}.Select(n=>Block(tag.Fields,n)).Where(b=>b!=null).ToArray();
  var fields=blocks.Length>0?blocks.SelectMany(b=>b.Elements.Cast<TagElement>()).SelectMany(e=>e.Fields).ToArray():tag.Fields;
  return AllReferences(fields).Where(r=>r.Path!=null && r.Path.Extension.StartsWith("shader",StringComparison.OrdinalIgnoreCase)).Select(r=>r.Path.RelativePath).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
 }
 static string[] MaterialOrder(TagFile tag) {
  // The tag's "materials" block in order: Tool fills it from the source materials,
  // so position k is the shader the k-th source material was imported with.
  var block=Block(tag.Fields,"materials");
  if(block==null)return new string[0];
  return block.Elements.Cast<TagElement>().Select(e=>AllReferences(e.Fields).Where(r=>r.Path!=null && r.Path.Extension.StartsWith("shader",StringComparison.OrdinalIgnoreCase)).Select(r=>r.Path.RelativePath).FirstOrDefault()??"").ToArray();
 }
 static List<object> SourceFiles(TagFile tag,string folder,string prefix) {
  var items=new List<object>();
  var stream=TagAlternateStreamType.TagImportInformation;
  if(!tag.DoesAlternateStreamExist(stream))return items;
  var files=F<TagFieldBlock>(((TagElement)tag.GetAlternateStream(stream)).Fields,"files");
  for(int i=0;i<files.Elements.Count;i++) {
   var f=files.Elements[i].Fields;string name=F<TagFieldElementLongString>(f,"path").Data??"";
   string lower=name.ToLowerInvariant();
   if(!lower.EndsWith(".ass") && !lower.EndsWith(".jms"))continue;
   byte[] zipped=F<TagFieldData>(f,"zipped data").GetData();
   string compressed=prefix+"-"+i+".zlib";
   // Never use embedded source names as output paths.
   using(var output=new FileStream(Path.Combine(folder,compressed),FileMode.CreateNew,FileAccess.Write))output.Write(zipped,0,zipped.Length);
   items.Add(new{source_path=name,compressed=compressed,size=I(f,"size"),crc32=unchecked((uint)I(f,"checksum"))});
  }
  return items;
 }
 static Dictionary<string,object> ReadObject(TagPath path,string folder,string prefix,List<string> warnings) {
  var result=new Dictionary<string,object>();
  result["tag"]=path.RelativePath;result["type"]=path.Extension;result["model"]="";result["render_model"]="";result["collision_model"]="";
  result["sources"]=new List<object>();result["shaders"]=new string[0];result["variants"]=new List<object>();result["regions"]=new List<object>();
  if(!File.Exists(path.Filename)){warnings.Add("Missing object tag: "+path.RelativePathWithExtension);return result;}
  Console.WriteLine("Reading "+path.RelativePathWithExtension);
  using(var item=new TagFile(path)) {
   result["default_variant"]=FindStringId(item.Fields,"default model variant")??"";
   var modelRef=References(item.Fields).FirstOrDefault(r=>r.FieldName=="model" && r.Path!=null);
   if(modelRef==null)return result;
   result["model"]=modelRef.Path.RelativePath;
   if(!File.Exists(modelRef.Path.Filename)){warnings.Add("Missing model tag: "+modelRef.Path.RelativePathWithExtension);return result;}
   using(var model=new TagFile(modelRef.Path)) {
    var refs=References(model.Fields).ToArray();
    var render=refs.FirstOrDefault(r=>r.FieldName=="render model" && r.Path!=null);
    var collision=refs.FirstOrDefault(r=>r.FieldName=="collision model" && r.Path!=null);
    if(collision!=null)result["collision_model"]=collision.Path.RelativePath;
    result["variants"]=NameTree(Block(model.Fields,"variants"),0);
    if(render==null)return result;
    result["render_model"]=render.Path.RelativePath;
    if(!File.Exists(render.Path.Filename)){warnings.Add("Missing render model tag: "+render.Path.RelativePathWithExtension);return result;}
    using(var mode=new TagFile(render.Path)) {
     // A render model whose stored source can't be read falls back to the map mesh.
     try {result["sources"]=SourceFiles(mode,folder,prefix);}
     catch(Exception e){warnings.Add("Render model "+render.Path.RelativePath+": its stored source files could not be read ("+e.Message+"); the map mesh is used.");}
     result["shaders"]=ShaderPaths(mode);
     result["material_order"]=MaterialOrder(mode);
     result["regions"]=NameTree(Block(mode.Fields,"regions"),0);
    }
   }
  }
  return result;
 }
 static void ScenarioScene(Job j) {
  string scenario=Safe(j.scenario);string folder=Path.GetDirectoryName(Path.GetFullPath(j.output));
  Directory.CreateDirectory(folder);
  var warnings=new List<string>();var bsps=new List<object>();var objects=new Dictionary<string,object>();
  var placements=new List<object>();var skies=new List<string>();var counts=new Dictionary<string,int>();
  using(var tag=new TagFile(TagPath.FromPathAndType(scenario,"scnr*"))) {
   var structure=Block(tag.Fields,"structure bsps");
   if(structure==null)throw new Exception("This scenario has no structure BSP block.");
   for(int i=0;i<structure.Elements.Count;i++) {
    var reference=References(structure.Elements[i].Fields).FirstOrDefault(r=>r.FieldName=="structure bsp" && r.Path!=null);
    if(reference==null){warnings.Add("BSP slot "+i+" has no structure BSP reference.");continue;}
    var row=new Dictionary<string,object>();row["index"]=i;row["tag"]=reference.Path.RelativePath;
    row["sources"]=new List<object>();row["shaders"]=new string[0];
    if(!File.Exists(reference.Path.Filename)){warnings.Add("Missing BSP tag: "+reference.Path.RelativePathWithExtension);row["missing"]=true;bsps.Add(row);continue;}
    try {
     Console.WriteLine("Reading "+reference.Path.RelativePathWithExtension);
     using(var bsp=new TagFile(reference.Path)) {row["sources"]=SourceFiles(bsp,folder,"bsp_"+i);row["shaders"]=ShaderPaths(bsp);row["material_order"]=MaterialOrder(bsp);}
    } catch(Exception e){warnings.Add("BSP "+reference.Path.RelativePath+": "+e.Message);}
    bsps.Add(row);
   }
   var names=Block(tag.Fields,"object names");
   var specs=new[]{new[]{"scenery","scenery palette","Scenery"},new[]{"crates","crate palette","Crates"},new[]{"machines","machine palette","Machines"},new[]{"controls","control palette","Controls"},new[]{"vehicles","vehicle palette","Vehicles"},new[]{"weapons","weapon palette","Weapons"},new[]{"equipment","equipment palette","Equipment"}};
   foreach(var spec in specs) {
    var block=Block(tag.Fields,spec[0]);var palette=Block(tag.Fields,spec[1]);
    if(block==null || palette==null)continue;
    counts[spec[2]]=block.Elements.Count;
    for(int i=0;i<block.Elements.Count;i++) {
     try {
      var f=block.Elements[i].Fields;
      int pi=F<TagFieldBlockIndex>(f,"type").Value;
      if(pi<0 || pi>=palette.Elements.Count){warnings.Add(spec[2]+" placement "+i+": no palette entry.");continue;}
      var reference=F<TagFieldReference>(palette.Elements[pi].Fields,"name").Path;
      if(reference==null){warnings.Add(spec[2]+" placement "+i+": empty palette entry.");continue;}
      string key=reference.RelativePathWithExtension;
      if(!objects.ContainsKey(key))objects[key]=ReadObject(reference,folder,"object_"+objects.Count,warnings);
      int ni=F<TagFieldBlockIndex>(f,"name").Value;
      string objectName=names!=null && ni>=0 && ni<names.Elements.Count?Text(names.Elements[ni].Fields,"name"):"";
      var data=S(f,"object data");
      placements.Add(new{category=spec[2],index=i,name=objectName,object_tag=key,variant=FindStringId(f,"variant name")??"",position=F<TagFieldElementArraySingle>(data,"position").Data,rotation=F<TagFieldElementArraySingle>(data,"rotation").Data,scale=F<TagFieldElementSingle>(data,"scale").Data});
     } catch(Exception e){warnings.Add(spec[2]+" placement "+i+": "+e.Message);}
    }
   }
   var skyBlock=Block(tag.Fields,"skies");
   if(skyBlock!=null)foreach(var e in skyBlock.Elements)foreach(var reference in AllReferences(e.Fields).Where(r=>r.Path!=null)) {
    string key=reference.Path.RelativePathWithExtension;
    try {if(!objects.ContainsKey(key))objects[key]=ReadObject(reference.Path,folder,"object_"+objects.Count,warnings);skies.Add(key);}
    catch(Exception error){warnings.Add("Sky "+key+": "+error.Message);}
   }
  }
  File.WriteAllText(j.output,js.Serialize(new{version=1,kind="halo3_scenario_tags",scenario=scenario,bsps=bsps,objects=objects,placements=placements,skies=skies,counts=counts,warnings=warnings}));
 }
 static void Collision(Job j) {
  using(var tag=new TagFile(TagPath.FromPathAndType(Safe(j.scenario),"sbsp*"))) {
   var ri=S(tag.Fields,"resource interface");var resources=F<TagFieldBlock>(ri,"raw_resources");
   int expectedDefinition=-1;
   if(!String.IsNullOrEmpty(j.asset_name)) {
    var instances=F<TagFieldBlock>(tag.Fields,"instanced geometry instances");
    foreach(var inst in instances.Elements)if(F<TagFieldElementStringID>(inst.Fields,"name").Data==j.asset_name)expectedDefinition=F<TagFieldBlockIndex>(inst.Fields,"instance definition").Value;
    if(expectedDefinition<0)throw new Exception("Source map and editing-kit tag do not contain the same named instance: "+j.asset_name);
   }
   var meshes=new List<object>();
   foreach(var raw in resources.Elements) {
    var defs=F<TagFieldBlock>(S(raw.Fields,"raw_items"),"instanced geometries definitions");
    for(int definitionIndex=0;definitionIndex<defs.Elements.Count;definitionIndex++) {var def=defs.Elements[definitionIndex];if(I(def.Fields,"mesh index")!=j.section)continue;
     if(expectedDefinition>=0 && definitionIndex!=expectedDefinition)throw new Exception("Source map/tag geometry indices differ; collision was not guessed.");
     var c=S(def.Fields,"collision info");     meshes.Add(CollisionFaces(c));
    }
   }
   if(meshes.Count!=1)throw new Exception("Could not uniquely match original collision definition; export is blocked until collision is supplied.");
   File.WriteAllText(j.output,js.Serialize(new{version=1,meshes=meshes,source=j.scenario,section=j.section}));Console.WriteLine("Original collision extracted");
  }
 }
}

