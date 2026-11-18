using System.Globalization;
using HaloBridge.H2ACampaign;

CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

const string Usage = """
HaloBridge.H2ACampaign - reads Halo 2 Anniversary campaign (Saber3D) .pck archives.

  list     <pck> [pattern]              List entries (tree). Pattern supports * and ?.
  header   <pck>                        Show the chunk table and root 1SERpak header.
  csvcheck <pck> [csv]                  Match the .csv beside the .pck against the directory.
  extract  <pck> <pattern> <outDir>     Write matching entries as raw files.
  pct      <pck|file.pct> [pattern] <outDir> [--dds] [--all-mips]
                                        Decode .pct textures to PNG (and optionally DDS).
  pctinfo  <pck|file.pct> [pattern]     Print texture headers.
  tpl      <pck|file.tpl> [pattern] <outDir>
                                        Export .tpl templates (props, sm_geom_*) to OBJ.
  lg       <pck|file.lg> [pattern] <outDir>
                                        Export a .lg scene's own geometry to OBJ.
  info     <pck|file> [pattern]         Dump the template/scene geometry structure.
  materials <pck|file.lg> [pattern]     List the distinct material property bags of a scene.
  map_scene <level.pck> <outDir> [--shared shared.pck] [--max-texture 2048] [--textures dir]
                                        Write a HaloBridge map scene (scene.json, mesh_N.json,
                                        DDS/PNG textures, optionally in a folder shared between
                                        levels) in classic Halo 2 world coordinates.
  asset_index <shared.pck> <out.json>   List placeable templates and materials (HaloBridge index).
  asset <shared.pck> <tag> <outDir> [--max-texture 2048] [--textures dir]
                                        Write one indexed asset as a HaloBridge preview.json.

A <pck> argument may be a level pak (01a_tutorial.pck) or shared.pck. Level paks list
textures and props with size 0: their data lives in shared.pck.
""";

if (args.Length == 0) { Console.WriteLine(Usage); return 1; }
try
{
    return args[0].ToLowerInvariant() switch
    {
        "list" => Commands.List(args),
        "header" => Commands.Header(args),
        "csvcheck" => Commands.CsvCheck(args),
        "extract" => Commands.Extract(args),
        "pct" => Commands.Pct(args),
        "pctinfo" => Commands.PctInfo(args),
        "tpl" or "lg" => Commands.Geometry(args),
        "info" => Commands.Info(args),
        "materials" => Commands.Materials(args),
        "map_scene" => Commands.MapScene(args),
        "asset_index" => Commands.AssetIndex(args),
        "asset" => Commands.Asset(args),
        _ => throw new ArgumentException("Unknown command.\n" + Usage),
    };
}
catch (Exception ex) when (ex is ArgumentException or InvalidDataException or IOException)
{
    Console.Error.WriteLine("error: " + ex.Message);
    return 2;
}
