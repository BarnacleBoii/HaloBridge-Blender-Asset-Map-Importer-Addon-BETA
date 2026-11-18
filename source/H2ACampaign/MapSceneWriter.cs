using System.Numerics;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace HaloBridge.H2ACampaign;

/// <summary>
/// Writes a Halo 2: Anniversary campaign level (.lg in a level .pck, textures from shared.pck) as a
/// HaloBridge "halo3_map_scene" folder, the same files the Extractor writes for .map files:
///   scene.json      placements (row-vector matrices, Halo world units) and mesh file names
///   mesh_N.json     {materials, meshes:[{positions, uv, normals, segments:[{material, indices}]}]}
///   tex_*.dds/.png  base and normal textures referenced by the materials (optionally in a shared folder)
/// The halo_bridge add-on imports it with map_scene.import_scene and converts the materials to
/// Halo 3 shaders like any other imported map.
///
/// Coordinates: Saber is Y-up metres; Halo is Z-up world units (10 ft). Fitted against the classic
/// Halo 2 01a_tutorial BSP: halo = (x, -z, y) / 3.048 with no offset (see FORMAT.md).
/// </summary>
public sealed class MapSceneWriter
{
    public const float MetresPerWorldUnit = 3.048f;
    public const string Game = "h2a";
    // Bumped when the output changes, so the add-on's cache re-extracts.
    public const int Version = 2;  // 2: DDS textures in a folder shared between levels

    public static Vector3 ToHalo(Vector3 v) => new Vector3(v.X, -v.Z, v.Y) / MetresPerWorldUnit;
    public static Vector3 ToHaloNormal(Vector3 n) => Vector3.Normalize(new Vector3(n.X, -n.Z, n.Y));

    readonly string _out;
    readonly string _textureDir;
    readonly int _maxTexture;
    readonly PckArchive _shared;
    readonly Dictionary<string, PckEntry> _textures = new(StringComparer.OrdinalIgnoreCase);
    readonly Dictionary<string, string?> _written = new(StringComparer.OrdinalIgnoreCase); // texture name -> png file (null = missing)
    readonly List<string> _warnings = [];
    readonly JsonWriterOptions _jsonOptions = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    MapSceneWriter(string output, PckArchive shared, int maxTexture, string textureDir)
    {
        _out = output; _shared = shared; _maxTexture = maxTexture; _textureDir = textureDir;
        Directory.CreateDirectory(textureDir);
        foreach (var e in shared.All)
            if (e.Size > 0 && !e.IsContainer && e.Extension == ".pct" && e.Category == "textures")
                _textures.TryAdd(Path.GetFileNameWithoutExtension(e.FileName), e);
    }

    void Progress(string message)
    {
        var temp = Path.Combine(_out, "progress.tmp");
        File.WriteAllText(temp, JsonSerializer.Serialize(new { message }));
        File.Move(temp, Path.Combine(_out, "progress.json"), true);
        Console.Error.WriteLine(message);
    }

    /// <param name="textureDir">
    /// Where decoded textures go. Levels can share one folder: textures come from shared.pck and many are
    /// reused between levels, so each is stored once. Defaults to the output folder.
    /// </param>
    public static void Export(string levelPak, string sharedPak, string output, int maxTexture, string? textureDir = null)
    {
        Directory.CreateDirectory(output);
        using var level = new PckArchive(levelPak);
        var lgEntry = level.All.FirstOrDefault(e => !e.IsContainer && e.Size > 0 && e.Extension == ".lg")
            ?? throw new InvalidDataException("This .pck has no .lg level scene (only campaign level paks do).");
        using var shared = new PckArchive(sharedPak);
        var w = new MapSceneWriter(output, shared, maxTexture, textureDir ?? output);
        w.Progress("Reading " + lgEntry.FileName);
        var model = SaberModel.Parse(level.ReadEntry(lgEntry), lgEntry.FileName);
        w.Write(model, Path.GetFileNameWithoutExtension(lgEntry.FileName));
    }

    sealed class MaterialInfo
    {
        public int Id;
        public string Name = "", Shader = "", Alpha = "opaque", Transparent = "";
        public string Base = "";
        public float TileU = 1, TileV = 1;
        public int UvSet;
    }

    static Dictionary<string, object?>? Dict(Dictionary<string, object?> d, string key) =>
        d.TryGetValue(key, out var v) ? v as Dictionary<string, object?> : null;
    static string Str(Dictionary<string, object?>? d, string key) => d != null && d.TryGetValue(key, out var v) && v is string s ? s : "";
    static float Num(Dictionary<string, object?>? d, string key, float fallback) =>
        d != null && d.TryGetValue(key, out var v) ? v switch { float f => f, int i => i, _ => fallback } : fallback;

    readonly Dictionary<string, MaterialInfo> _materials = [];

    MaterialInfo MaterialFor(GeometrySubMesh s)
    {
        var layer = Dict(s.Material, "layer0");
        var tex = Str(layer, "texName");
        if (tex.Length == 0) tex = Str(s.Material, "shadingMtl_Tex");
        var preset = Str(layer, "mtlName");
        var transparency = Dict(Dict(s.Material, "extraParams"), "transparency");
        bool transparent = Num(transparency, "enabled", 0) != 0;
        float tu = Num(layer, "tilingU", 1), tv = Num(layer, "tilingV", 1);
        int uvSet = (int)Num(layer, "uvSetIdx", 0);
        if (uvSet < 0) uvSet = 0;
        string alpha = "opaque", blend = "";
        if (preset.Contains("glass", StringComparison.OrdinalIgnoreCase) && !preset.StartsWith("notransp", StringComparison.OrdinalIgnoreCase))
        { alpha = "blend"; blend = "alpha"; }
        else if (transparent || preset.Equals("decal", StringComparison.OrdinalIgnoreCase) || tex.Contains("decal", StringComparison.OrdinalIgnoreCase))
            alpha = "clip";
        var key = $"{tex}|{preset}|{alpha}|{tu}|{tv}|{uvSet}";
        if (_materials.TryGetValue(key, out var m)) return m;
        // Shader names stay unique per texture + preset + mode so Halo 3 gets one shader each.
        var name = tex + (preset is "" or "default" ? "" : "_" + preset) + (alpha == "opaque" ? "" : "_" + alpha) +
                   (tu != 1 || tv != 1 ? $"_x{tu:0.##}x{tv:0.##}" : "") + (uvSet != 0 ? $"_uv{uvSet}" : "");
        m = new MaterialInfo
        {
            Id = _materials.Count, Name = name, Shader = "h2a_campaign\\" + name, Alpha = alpha, Transparent = blend,
            Base = tex, TileU = tu, TileV = tv, UvSet = uvSet,
        };
        _materials[key] = m;
        return m;
    }

    /// <summary>
    /// Writes a texture from shared.pck once, at the first mip no wider than _maxTexture: block-compressed
    /// formats as a single-mip DDS (the game's own data, about a quarter of a PNG's size), others as PNG.
    /// Returns its path relative to the scene folder (texture folders can be shared), or null.
    /// </summary>
    string? Texture(string name)
    {
        lock (_written) if (_written.TryGetValue(name, out var done)) return done;
        string? file = null;
        if (_textures.TryGetValue(name, out var entry))
        {
            try
            {
                var safe = "tex_" + string.Concat(name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c));
                var existing = new[] { ".dds", ".png" }.Select(x => Path.Combine(_textureDir, safe + x)).FirstOrDefault(File.Exists);
                if (existing == null)
                {
                    byte[] raw;
                    lock (_shared) raw = _shared.ReadEntry(entry);  // the archive reader is not thread-safe
                    var pic = Picture.Parse(raw);
                    int mip = 0;
                    while (mip + 1 < Math.Max(1, pic.MipCount) && Math.Max(pic.Width >> mip, pic.Height >> mip) > _maxTexture) mip++;
                    int w = Math.Max(1, pic.Width >> mip), h = Math.Max(1, pic.Height >> mip);
                    // Keep whichever file is smaller. Measured on 120 campaign textures: BC1 is almost always
                    // smaller as DDS (53/55), so it isn't PNG-encoded; BC5 normal maps are about half the size
                    // as optimized PNG (51/54); BC3/BC4 vary, so both are tried.
                    byte[]? dds = pic.IsBlockCompressed ? pic.ToDdsMip(mip) : null;
                    bool tryPng = dds == null || pic.Format is not (PictureFormat.OXT1 or PictureFormat.AXT1 or PictureFormat.DXT3);
                    byte[]? png = tryPng ? Png.Encode(pic.DecodeRgba(0, mip), w, h, small: true) : null;
                    bool usePng = png != null && (dds == null || png.Length < dds.Length);
                    existing = Path.Combine(_textureDir, safe + (usePng ? ".png" : ".dds"));
                    // Written under a temporary name and moved, so a level exporting at the same time never
                    // sees a half-written file in a shared texture folder.
                    var temp = existing + "." + Environment.ProcessId + "." + Environment.CurrentManagedThreadId + ".tmp";
                    File.WriteAllBytes(temp, usePng ? png! : dds!);
                    File.Move(temp, existing, true);
                }
                file = Path.GetRelativePath(_out, existing).Replace('\\', '/');
            }
            catch (Exception ex) when (ex is InvalidDataException or NotSupportedException)
            {
                lock (_warnings) _warnings.Add($"Texture {name}: {ex.Message}");
                file = null;
            }
        }
        lock (_written) _written[name] = file;
        return file;
    }

    /// <summary>Prepares every texture the kept submeshes use, in parallel (PNG encoding is the slow part).</summary>
    void PrepareTextures(IEnumerable<GeometrySubMesh> kept)
    {
        var names = kept.Select(MaterialFor).Select(m => m.Base).Where(n => n.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase)
            .SelectMany(n => new[] { n, n + "_nm" }).Where(n => !_written.ContainsKey(n)).ToList();
        int done = 0;
        Parallel.ForEach(names, new ParallelOptions { MaxDegreeOfParallelism = Math.Max(1, Environment.ProcessorCount - 1) }, name =>
        {
            Texture(name);
            int n = Interlocked.Increment(ref done);
            if (n % 20 == 0 || n == names.Count) lock (_out) Progress($"Preparing textures {n}/{names.Count}");
        });
    }

    object MaterialJson(MaterialInfo m)
    {
        var textures = new List<object>();
        var baseFile = Texture(m.Base);
        if (baseFile != null)
            textures.Add(new { name = m.Base, parameter = "layer0", usage = "diffuse", path = baseFile, tiling = new[] { m.TileU, m.TileV }, gamma = 2.2f, channels = 15, blend_channel = 0 });
        else _warnings.Add("Missing texture: " + m.Base + " (material " + m.Name + ")");
        var normalFile = Texture(m.Base + "_nm");
        if (normalFile != null)
            textures.Add(new { name = m.Base + "_nm", parameter = "layer0", usage = "normal", path = normalFile, tiling = new[] { m.TileU, m.TileV }, gamma = 1f, channels = 15, blend_channel = 0 });
        var options = new Dictionary<string, string>();
        if (m.Transparent.Length > 0) options["transparent"] = m.Transparent;
        return new { id = m.Id, name = m.Name, shader = m.Shader, alpha = m.Alpha, source_game = Game, options, tints = Array.Empty<object>(), textures };
    }

    void Write(SaberModel model, string levelName)
    {
        var nonLod0 = model.NonLod0ObjectIds();
        var byOwner = new Dictionary<SaberObject, List<GeometrySubMesh>>();
        int skippedLod = 0, skippedHelper = 0, skippedPlaceholder = 0;
        foreach (var s in model.SubMeshes)
        {
            var owner = model.ObjectFor(s);
            if (owner == null) continue;
            if (nonLod0.Contains(owner.Id)) { skippedLod++; continue; }
            if (SaberModel.IsHelper(owner)) { skippedHelper++; continue; }
            if (SaberModel.IsPlaceholderMaterial(s)) { skippedPlaceholder++; continue; }
            if (!byOwner.TryGetValue(owner, out var list)) byOwner[owner] = list = [];
            list.Add(s);
        }
        PrepareTextures(byOwner.Values.SelectMany(s => s));
        var meshes = new Dictionary<string, string>();
        var placements = new List<object>();
        var counts = new Dictionary<string, int>();
        var identity = new[] { new[] { 1f, 0, 0, 0 }, new[] { 0f, 1, 0, 0 }, new[] { 0f, 0, 1, 0 }, new[] { 0f, 0, 0, 1 } };
        int index = 0;
        foreach (var (owner, subs) in byOwner)
        {
            index++;
            if (index % 100 == 1) Progress($"Writing level piece {index}/{byOwner.Count}: {owner.DisplayName}");
            var key = $"{levelName}|{owner.Id}";
            var file = $"mesh_{meshes.Count}.json";
            var usedMaterials = new Dictionary<int, MaterialInfo>();
            var positions = new List<Vector3>(); var uvs = new List<Vector2>(); var normals = new List<Vector3>();
            var segments = new List<(int material, List<int> indices)>();
            bool anyUv = false, allNormals = true;
            foreach (var s in subs)
            {
                var mat = MaterialFor(s);
                SaberModel.MeshData md;
                try { md = model.BuildSubMesh(s, true, mat.UvSet); }
                catch (Exception ex) when (ex is InvalidDataException or EndOfStreamException or ArgumentOutOfRangeException)
                { _warnings.Add($"{owner.DisplayName}: submesh skipped ({ex.Message})"); continue; }
                if (md.Faces.Count == 0) continue;
                usedMaterials[mat.Id] = mat;
                int baseIndex = positions.Count;
                positions.AddRange(md.Positions.Select(ToHalo));
                if (md.Uvs.Count == md.Positions.Count) { uvs.AddRange(md.Uvs); anyUv = true; }
                else uvs.AddRange(Enumerable.Repeat(Vector2.Zero, md.Positions.Count));
                if (md.Normals.Count == md.Positions.Count) normals.AddRange(md.Normals.Select(ToHaloNormal));
                else { allNormals = false; normals.AddRange(Enumerable.Repeat(Vector3.UnitZ, md.Positions.Count)); }
                var indices = new List<int>(md.Faces.Count * 3);
                foreach (var (a, b, c) in md.Faces) { indices.Add(baseIndex + a); indices.Add(baseIndex + b); indices.Add(baseIndex + c); }
                segments.Add((mat.Id, indices));
            }
            if (segments.Count == 0) continue;
            WriteMesh(Path.Combine(_out, file), usedMaterials.Values.Select(MaterialJson).ToList(), positions, anyUv ? uvs : null, allNormals ? normals : null, segments);
            meshes[key] = file;
            var group = subs.All(s => MaterialFor(s).Alpha == "clip" && MaterialFor(s).Base.Contains("decal", StringComparison.OrdinalIgnoreCase)) ? "Decals"
                      : subs.All(s => MaterialFor(s).Alpha == "blend") ? "Glass" : "Level geometry";
            placements.Add(new { name = owner.DisplayName.TrimStart('.') + " #" + owner.Id, mesh = key, group, source_tag = "h2a_campaign\\" + levelName, matrix = identity });
            counts[group] = counts.GetValueOrDefault(group) + 1;
        }
        if (skippedLod > 0) _warnings.Add($"{skippedLod} lower level-of-detail submeshes left out (LOD0 only).");
        if (skippedHelper > 0) _warnings.Add($"{skippedHelper} engine helper submeshes left out (occluders, shadow casters, reflection boxes).");
        if (skippedPlaceholder > 0) _warnings.Add($"{skippedPlaceholder} untextured placeholder submeshes left out.");
        int layered = model.SubMeshes.Count(s => Dict(s.Material, "layer1") != null);
        if (layered > 0) _warnings.Add($"{layered} submeshes blend extra material layers by vertex colour; only their first layer is used.");
        var missing = _written.Count(kv => kv.Value == null && !kv.Key.EndsWith("_nm"));
        Progress($"Writing scene manifest ({placements.Count} pieces, {_materials.Count} materials, {_written.Count(kv => kv.Value != null)} textures)");
        var scene = new
        {
            version = 1,
            kind = "halo3_map_scene",
            game = Game,
            source = "h2a_campaign",
            exporter_version = Version,
            scenario = "h2a_campaign\\" + levelName,
            units = "halo",
            matrix_convention = "row_vector",
            expected_bsps = 1,
            decoded_bsps = 1,
            meshes,
            placements,
            counts,
            warnings = _warnings.Distinct().ToArray(),
            limitations = new[]
            {
                "Remastered (Saber3D) visual geometry only, placed in classic Halo 2 world coordinates.",
                "Collision is generated from the visual geometry; AI, weapons, vehicles, scripts and lighting are not imported.",
                "Materials use their first texture layer; vertex-blended layers, specular maps and lightmaps are not converted.",
            },
        };
        File.WriteAllText(Path.Combine(_out, "scene.json"), JsonSerializer.Serialize(scene, new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
        Progress($"Level scene extracted: {placements.Count} pieces");
    }

    // ---- Individual assets (the add-on's Indexed Asset List) ------------------------------------------

    static readonly string[] TextureCompanions = ["_nm", "_spec", "_em", "_det", "_mask", "_illum"];

    /// <summary>
    /// Lists shared.pck's placeable assets as a HaloBridge index: every template (prop, weapon, character,
    /// vehicle) with visible LOD0 geometry as a "model", and every base texture (not a _nm/_spec/... companion)
    /// as a "material" made of the texture and its normal map.
    /// </summary>
    public static void Index(string sharedPak, string output)
    {
        using var shared = new PckArchive(sharedPak);
        var assets = new List<object>();
        var warnings = new List<string>();
        var templates = shared.All.Where(e => !e.IsContainer && e.Size > 0 && e.Extension == ".tpl" && e.Category == "tpl").ToList();
        int index = 0;
        foreach (var e in templates)
        {
            if (++index % 100 == 1) Console.Error.WriteLine($"Indexing templates {index}/{templates.Count}");
            try
            {
                var model = SaberModel.Parse(shared.ReadEntry(e), e.FileName);
                var hidden = model.NonLod0ObjectIds();
                bool visible = model.SubMeshes.Any(s => model.ObjectFor(s) is { } o && !hidden.Contains(o.Id) && !SaberModel.IsHelper(o) && !SaberModel.IsPlaceholderMaterial(s) && s.FaceCount > 0);
                // Some skinned characters' parts are stored relative to their bones and aren't assembled yet:
                // say so in the asset list. (Variants and damage states are switchable parts, not a problem.)
                bool skinned = model.SubMeshes.Any(s => s.BoneIds.Length > 0);
                var note = skinned ? "Rigged model, static rest pose: some characters' parts are out of place" : "";
                if (visible) assets.Add(new { tag = e.RawName, kind = "model", name = Path.GetFileNameWithoutExtension(e.FileName), section = -1, scenery_tag = "", note });
            }
            catch (Exception ex) when (ex is InvalidDataException or NotSupportedException or EndOfStreamException or ArgumentOutOfRangeException)
            { warnings.Add($"Template {e.FileName}: {ex.Message}"); }
        }
        var textures = shared.All.Where(e => !e.IsContainer && e.Size > 0 && e.Extension == ".pct" && e.Category == "textures")
            .Select(e => Path.GetFileNameWithoutExtension(e.FileName)).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        foreach (var name in textures.Where(n => !TextureCompanions.Any(c => n.EndsWith(c, StringComparison.OrdinalIgnoreCase))).OrderBy(n => n))
            assets.Add(new { tag = "<textures>:" + name + ".pct", kind = "material", name, section = -1, scenery_tag = "" });
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllText(output, JsonSerializer.Serialize(new { version = 1, game = Game, source = "h2a_campaign", map = sharedPak, assets, warnings },
            new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }));
        Console.Error.WriteLine($"Indexed {assets.Count} assets.");
    }

    /// <summary>
    /// One indexed asset as a HaloBridge preview.json in <paramref name="output"/>: a template's visible LOD0
    /// geometry in Halo world units (each object's transform applied) with its materials, or a material
    /// (texture + normal map) with no geometry. Textures go to <paramref name="textureDir"/>.
    /// </summary>
    public static void ExportAsset(string sharedPak, string tag, string output, int maxTexture, string? textureDir)
    {
        Directory.CreateDirectory(output);
        using var shared = new PckArchive(sharedPak);
        var w = new MapSceneWriter(output, shared, maxTexture, textureDir ?? output);
        var extra = new Dictionary<string, object> { ["tag"] = tag, ["section"] = -1, ["units"] = "halo", ["collision"] = "missing", ["selection_policy"] = 0, ["selection"] = Array.Empty<object>() };
        if (tag.StartsWith("<textures>:", StringComparison.OrdinalIgnoreCase))
        {
            var name = Path.GetFileNameWithoutExtension(tag["<textures>:".Length..]);
            var m = new MaterialInfo { Id = 0, Name = name, Shader = "h2a_campaign\\" + name, Base = name };
            var material = w.MaterialJson(m);
            extra["warnings"] = w._warnings.ToArray();
            w.WriteMesh(Path.Combine(output, "preview.json"), [material], [], null, null, [], extra);
            return;
        }
        var entry = shared.All.FirstOrDefault(e => !e.IsContainer && e.Size > 0 && e.RawName.Equals(tag, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidDataException("Asset not found in shared.pck: " + tag);
        var model = SaberModel.Parse(shared.ReadEntry(entry), entry.FileName);
        // Variants, damage states and lower LODs become switchable parts (HaloBridge's part toggles) instead of
        // being dropped; skin compounds and helpers are left out.
        var classes = model.ClassifyParts();
        var kept = model.SubMeshes.Where(s => model.ObjectFor(s) is { } o && classes.GetValueOrDefault(o.Id) != null && !SaberModel.IsPlaceholderMaterial(s)).ToList();
        w.PrepareTextures(kept);
        var used = new Dictionary<int, MaterialInfo>();
        var parts = new Dictionary<string, Part>();
        foreach (var s in kept)
        {
            var choice = classes[model.ObjectFor(s)!.Id]!.Value;
            var key = choice.Region + "/" + choice.Permutation;
            if (!parts.TryGetValue(key, out var part))
                parts[key] = part = new Part { Region = choice.Region, Permutation = choice.Permutation, Choice = key, Enabled = choice.Enabled, SourceMesh = parts.Count };
            var mat = w.MaterialFor(s);
            SaberModel.MeshData md;
            try { md = model.BuildSubMesh(s, true, mat.UvSet); }
            catch (Exception ex) when (ex is InvalidDataException or EndOfStreamException or ArgumentOutOfRangeException)
            { w._warnings.Add("Submesh skipped: " + ex.Message); continue; }
            if (md.Faces.Count == 0) continue;
            used[mat.Id] = mat;
            int baseIndex = part.Positions.Count;
            part.Positions.AddRange(md.Positions.Select(ToHalo));
            if (md.Uvs.Count == md.Positions.Count) { part.Uvs.AddRange(md.Uvs); part.AnyUv = true; } else part.Uvs.AddRange(Enumerable.Repeat(Vector2.Zero, md.Positions.Count));
            if (md.Normals.Count == md.Positions.Count) part.Normals.AddRange(md.Normals.Select(ToHaloNormal));
            else { part.AllNormals = false; part.Normals.AddRange(Enumerable.Repeat(Vector3.UnitZ, md.Positions.Count)); }
            part.Segments.Add((mat.Id, md.Faces.SelectMany(f => new[] { baseIndex + f.A, baseIndex + f.B, baseIndex + f.C }).ToList()));
        }
        var all = parts.Values.Where(p => p.Segments.Count > 0).OrderBy(p => p.Region == "body" ? 0 : 1).ThenBy(p => p.Region).ThenBy(p => p.Permutation).ToList();
        if (all.Count == 0) throw new InvalidDataException("This template has no visible geometry.");
        if (!all.Any(p => p.Enabled)) all[0].Enabled = true;
        if (model.SubMeshes.Any(s => s.BoneIds.Length > 0)) w._warnings.Add("Rigged model: exported in its rest pose, without bones or animation.");
        extra["warnings"] = w._warnings.Distinct().ToArray();
        var materials = used.Values.Select(w.MaterialJson).ToList();
        if (all.Count > 1)
        {
            // Same layout as the extractor's model parts: parts.json holds every choice, preview.json the
            // default selection; the add-on's part toggles rebuild the mesh from parts.json.
            extra["selection_policy"] = 2;
            extra["selection"] = all.GroupBy(p => p.Region).Select(g => new
            {
                region = g.Key,
                selected = g.Where(p => p.Enabled).Select(p => p.Permutation).ToArray(),
                available = g.Select(p => p.Permutation).ToArray(),
                instanced = false,
            }).ToArray();
            w.WriteParts(Path.Combine(output, "parts.json"), materials, all, new Dictionary<string, object>());
            w.WriteParts(Path.Combine(output, "preview.json"), materials, all.Where(p => p.Enabled).ToList(), extra);
        }
        else w.WriteParts(Path.Combine(output, "preview.json"), materials, all, extra, partFields: false);
    }

    sealed class Part
    {
        public string Region = "", Permutation = "", Choice = "";
        public bool Enabled, AnyUv, AllNormals = true;
        public int SourceMesh;
        public List<Vector3> Positions = [], Normals = [];
        public List<Vector2> Uvs = [];
        public List<(int material, List<int> indices)> Segments = [];
    }

    void WriteParts(string path, List<object> materials, List<Part> parts, Dictionary<string, object> extra, bool partFields = true)
    {
        using var fs = File.Create(path);
        using var j = new Utf8JsonWriter(fs, _jsonOptions);
        j.WriteStartObject();
        j.WriteNumber("version", 1);
        foreach (var (key, value) in extra)
        {
            j.WritePropertyName(key);
            JsonSerializer.Serialize(j, value, value.GetType());
        }
        j.WritePropertyName("materials");
        JsonSerializer.Serialize(j, materials);
        j.WriteStartArray("meshes");
        foreach (var p in parts)
        {
            j.WriteStartObject();
            if (partFields)
            {
                j.WriteString("name", p.Region + " / " + p.Permutation);
                j.WriteNumber("source_mesh", p.SourceMesh);
                j.WriteString("region", p.Region);
                j.WriteString("permutation", p.Permutation);
                j.WriteString("choice", p.Choice);
                j.WriteBoolean("enabled", p.Enabled);
            }
            WriteGeometry(j, p.Positions, p.AnyUv ? p.Uvs : null, p.AllNormals ? p.Normals : null, p.Segments);
            j.WriteEndObject();
        }
        j.WriteEndArray();
        j.WriteEndObject();
    }

    void WriteMesh(string path, List<object> materials, List<Vector3> positions, List<Vector2>? uvs, List<Vector3>? normals, List<(int material, List<int> indices)> segments, Dictionary<string, object>? extra = null)
    {
        using var fs = File.Create(path);
        using var j = new Utf8JsonWriter(fs, _jsonOptions);
        j.WriteStartObject();
        j.WriteNumber("version", 1);
        foreach (var (key, value) in extra ?? [])
        {
            j.WritePropertyName(key);
            JsonSerializer.Serialize(j, value, value.GetType());
        }
        j.WritePropertyName("materials");
        JsonSerializer.Serialize(j, materials);
        j.WriteStartArray("meshes");
        j.WriteStartObject();
        WriteGeometry(j, positions, uvs, normals, segments);
        j.WriteEndObject();
        j.WriteEndArray();
        j.WriteEndObject();
    }

    static void WriteGeometry(Utf8JsonWriter j, List<Vector3> positions, List<Vector2>? uvs, List<Vector3>? normals, List<(int material, List<int> indices)> segments)
    {
        j.WriteStartArray("positions");
        foreach (var p in positions) { j.WriteStartArray(); j.WriteNumberValue(R(p.X)); j.WriteNumberValue(R(p.Y)); j.WriteNumberValue(R(p.Z)); j.WriteEndArray(); }
        j.WriteEndArray();
        if (uvs != null)
        {
            j.WriteStartArray("uv");
            foreach (var t in uvs) { j.WriteStartArray(); j.WriteNumberValue(R(t.X)); j.WriteNumberValue(R(t.Y)); j.WriteEndArray(); }
            j.WriteEndArray();
        }
        else j.WriteNull("uv");
        if (normals != null)
        {
            j.WriteStartArray("normals");
            foreach (var n in normals) { j.WriteStartArray(); j.WriteNumberValue(R(n.X)); j.WriteNumberValue(R(n.Y)); j.WriteNumberValue(R(n.Z)); j.WriteEndArray(); }
            j.WriteEndArray();
        }
        else j.WriteNull("normals");
        j.WriteStartArray("segments");
        foreach (var (material, indices) in segments)
        {
            j.WriteStartObject();
            j.WriteNumber("material", material);
            j.WriteStartArray("indices");
            foreach (var i in indices) j.WriteNumberValue(i);
            j.WriteEndArray();
            j.WriteEndObject();
        }
        j.WriteEndArray();
    }

    static double R(float v) => Math.Round(v, 5);
}
