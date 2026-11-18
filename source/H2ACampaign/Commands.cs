namespace HaloBridge.H2ACampaign;

static class Commands
{
    static string Arg(string[] a, int i, string what) =>
        i < a.Length ? a[i] : throw new ArgumentException($"Missing {what}.");

    static bool IsPak(string path) => path.EndsWith(".pck", StringComparison.OrdinalIgnoreCase);

    /// <summary>Yields (name, bytes) for a pak + pattern, or a single loose file. Returns remaining args.</summary>
    static List<(string Name, Func<byte[]> Load)> Inputs(string[] a, out string[] rest, string defaultPattern, out PckArchive? pak, bool needsOutDir = false)
    {
        var src = Arg(a, 1, "input");
        if (IsPak(src))
        {
            pak = new PckArchive(src);
            int positional = a.Skip(2).Count(x => !x.StartsWith("--"));
            var hasPattern = positional >= (needsOutDir ? 2 : 1);
            if (!hasPattern && defaultPattern == "") throw new ArgumentException("Give an entry name or pattern.");
            var pattern = hasPattern ? a[2] : defaultPattern;
            rest = a.Skip(hasPattern ? 3 : 2).ToArray();
            var p = pak;
            var hits = p.Find(pattern).Where(e => !e.IsContainer).ToList();
            if (hits.Count == 0) throw new ArgumentException($"No non-empty entry matches '{pattern}'. (Size-0 entries live in shared.pck.)");
            return hits.Select(e => (e.Path, (Func<byte[]>)(() => p.ReadEntry(e)))).ToList();
        }
        pak = null;
        rest = a.Skip(2).ToArray();
        return [(Path.GetFileName(src), () => File.ReadAllBytes(src))];
    }

    public static int List(string[] a)
    {
        using var pak = new PckArchive(Arg(a, 1, "pck"));
        var pattern = a.Length > 2 ? a[2] : "*";
        var hits = pak.Find(pattern, includeEmpty: true).ToHashSet();
        int shown = 0;
        foreach (var e in pak.All)
        {
            if (!hits.Contains(e)) continue;
            Console.WriteLine($"{new string(' ', e.Depth * 2)}{e.Offset,12:X} {e.Size,11} {e.RawName}{(e.IsContainer ? $"  [1SERpak, {e.Children.Count}]" : "")}");
            shown++;
        }
        Console.Error.WriteLine($"{shown} of {pak.All.Count} entries ({pak.Roots.Count} top-level, {pak.All.Count(e => e.Size == 0)} size-0 references).");
        return 0;
    }

    public static int Header(string[] a)
    {
        using var pak = new PckArchive(Arg(a, 1, "pck"));
        var d = pak.Data;
        Console.WriteLine($"chunks={d.ChunkCount} compressed={d.IsCompressed} uncompressed={d.Length} (0x{d.Length:X})");
        Console.WriteLine("root 1SERpak header (0x45 bytes):");
        Console.WriteLine(Hex(pak.RootHeader));
        Console.WriteLine($"entry count={pak.Roots.Count} unk={pak.RootUnknown} (0x{pak.RootUnknown:X})");
        foreach (var c in pak.All.Where(e => e.IsContainer).Take(3))
        {
            Console.WriteLine($"nested {c.RawName}:");
            Console.WriteLine(Hex(pak.Data.Read(c.Offset, PckArchive.PakHeaderSize + 8)));
        }
        return 0;
    }

    public static string Hex(byte[] b) =>
        string.Join("\n", b.Chunk(16).Select((r, i) => $"  {i * 16:X4}: {string.Join(' ', r.Select(x => x.ToString("X2")))}"));

    public static int CsvCheck(string[] a)
    {
        var pck = Arg(a, 1, "pck");
        var csv = a.Length > 2 ? a[2] : Path.ChangeExtension(pck, ".csv");
        using var pak = new PckArchive(pck);
        var byName = pak.All.GroupBy(e => e.RawName).ToDictionary(g => g.Key, g => g.ToList());
        int lines = 0, matched = 0, sizeMismatch = 0, missing = 0;
        foreach (var raw in File.ReadLines(csv))
        {
            if (string.IsNullOrWhiteSpace(raw)) continue;
            lines++;
            var line = raw;
            int depth = 0;
            while (line.StartsWith("- ")) { line = line[2..]; depth++; }
            int comma = line.LastIndexOf(',');
            var name = line[..comma];
            var size = int.Parse(line[(comma + 1)..]);
            if (!byName.TryGetValue(name, out var list)) { if (missing++ < 10) Console.WriteLine($"missing: {raw}"); continue; }
            if (list.Any(e => e.Size == size && e.Depth == depth)) matched++;
            else if (sizeMismatch++ < 10) Console.WriteLine($"size/depth mismatch: {raw} vs {string.Join(",", list.Select(e => $"{e.Size}@{e.Depth}"))}");
        }
        Console.WriteLine($"csv lines={lines} matched={matched} sizeMismatch={sizeMismatch} missing={missing}; pak entries={pak.All.Count}");
        return missing + sizeMismatch == 0 ? 0 : 1;
    }

    public static int Extract(string[] a)
    {
        using var pak = new PckArchive(Arg(a, 1, "pck"));
        var pattern = Arg(a, 2, "pattern");
        var outDir = Arg(a, 3, "output folder");
        int n = 0;
        foreach (var e in pak.Find(pattern))
        {
            var rel = SafeRelative(e);
            var dst = Path.Combine(outDir, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
            File.WriteAllBytes(dst, pak.ReadEntry(e));
            Console.WriteLine($"{e.Size,11} {rel}");
            n++;
        }
        Console.Error.WriteLine($"{n} entries extracted.");
        return n > 0 ? 0 : 1;
    }

    static string SafeRelative(PckEntry e)
    {
        var parts = new List<string>();
        for (var x = e; x != null; x = x.Parent)
        {
            var p = x.Path;
            if (x.Parent == null && x.Category.Length > 0) p = Path.Combine(x.Category, p);
            parts.Insert(0, x.IsContainer && x != e ? p + ".pak" : p);
        }
        var rel = Path.Combine(parts.ToArray());
        var clean = string.Join(Path.DirectorySeparatorChar,
            rel.Split('\\', '/').Where(s => s.Length > 0 && s != "." && s != "..")
               .Select(s => string.Concat(s.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c))));
        return clean;
    }

    public static int PctInfo(string[] a)
    {
        var inputs = Inputs(a, out _, "*.pct", out var pak);
        using (pak)
            foreach (var (name, load) in inputs)
            {
                try { Console.WriteLine($"{name}: {Picture.Parse(load())}"); }
                catch (InvalidDataException ex) { Console.WriteLine($"{name}: ERROR {ex.Message}"); }
            }
        return 0;
    }

    public static int Pct(string[] a)
    {
        var inputs = Inputs(a, out var rest, "*.pct", out var pak, needsOutDir: true);
        using (pak)
        {
            var outDir = rest.FirstOrDefault(r => !r.StartsWith("--")) ?? throw new ArgumentException("Missing output folder.");
            bool dds = rest.Contains("--dds"), allMips = rest.Contains("--all-mips");
            int ok = 0, fail = 0;
            foreach (var (name, load) in inputs)
            {
                if (!name.EndsWith(".pct", StringComparison.OrdinalIgnoreCase)) continue;
                try
                {
                    var pic = Picture.Parse(load());
                    var baseName = Path.Combine(outDir, Path.GetFileNameWithoutExtension(name));
                    Directory.CreateDirectory(outDir);
                    foreach (var f in pic.WritePngs(baseName, allMips)) Console.WriteLine($"{f}  ({pic})");
                    if (dds) { File.WriteAllBytes(baseName + ".dds", pic.ToDds()); }
                    ok++;
                }
                catch (Exception ex) when (ex is InvalidDataException or NotSupportedException)
                {
                    Console.WriteLine($"{name}: FAILED {ex.Message}");
                    fail++;
                }
            }
            Console.Error.WriteLine($"{ok} textures decoded, {fail} failed.");
            return fail == 0 && ok > 0 ? 0 : 1;
        }
    }

    public static int Geometry(string[] a)
    {
        var isLg = a[0].Equals("lg", StringComparison.OrdinalIgnoreCase);
        var inputs = Inputs(a, out var rest, isLg ? "*.lg" : "*.tpl", out var pak, needsOutDir: true);
        using (pak)
        {
            var outDir = rest.FirstOrDefault(r => !r.StartsWith("--")) ?? throw new ArgumentException("Missing output folder.");
            bool allLods = rest.Contains("--all-lods"), helpers = rest.Contains("--helpers");
            Directory.CreateDirectory(outDir);
            int ok = 0, fail = 0;
            foreach (var (name, load) in inputs)
            {
                try
                {
                    var model = SaberModel.Parse(load(), name);
                    var dst = Path.Combine(outDir, Path.GetFileNameWithoutExtension(name) + ".obj");
                    var stats = ObjWriter.Write(model, dst, allLods, helpers);
                    Console.WriteLine($"{dst}  {stats}");
                    ok++;
                }
                catch (Exception ex) when (ex is InvalidDataException or NotSupportedException or EndOfStreamException or ArgumentOutOfRangeException or IndexOutOfRangeException)
                {
                    Console.WriteLine($"{name}: FAILED {ex.GetType().Name}: {ex.Message}");
                    fail++;
                }
            }
            Console.Error.WriteLine($"{ok} exported, {fail} failed.");
            return fail == 0 && ok > 0 ? 0 : 1;
        }
    }

    /// <summary>map_scene &lt;level.pck&gt; &lt;outDir&gt; [--shared shared.pck] [--max-texture 2048]: HaloBridge map scene folder.</summary>
    public static int MapScene(string[] a)
    {
        var level = Arg(a, 1, "level .pck");
        var outDir = Arg(a, 2, "output folder");
        string Option(string name, string fallback) { int i = Array.IndexOf(a, name); return i >= 0 && i + 1 < a.Length ? a[i + 1] : fallback; }
        var shared = Option("--shared", Path.Combine(Path.GetDirectoryName(Path.GetFullPath(level))!, "shared.pck"));
        if (!File.Exists(shared)) throw new ArgumentException("shared.pck not found next to the level (" + shared + "); pass --shared.");
        int max = int.Parse(Option("--max-texture", "2048"));
        var textures = Option("--textures", "");
        MapSceneWriter.Export(level, shared, outDir, max, textures.Length > 0 ? textures : null);
        return 0;
    }

    /// <summary>asset_index &lt;shared.pck&gt; &lt;out.json&gt; / asset &lt;shared.pck&gt; &lt;tag&gt; &lt;outDir&gt; [--max-texture N] [--textures dir]</summary>
    public static int AssetIndex(string[] a)
    {
        MapSceneWriter.Index(Arg(a, 1, "shared.pck"), Arg(a, 2, "output .json"));
        return 0;
    }

    public static int Asset(string[] a)
    {
        string Option(string name, string fallback) { int i = Array.IndexOf(a, name); return i >= 0 && i + 1 < a.Length ? a[i + 1] : fallback; }
        var textures = Option("--textures", "");
        MapSceneWriter.ExportAsset(Arg(a, 1, "shared.pck"), Arg(a, 2, "asset tag"), Arg(a, 3, "output folder"),
            int.Parse(Option("--max-texture", "2048")), textures.Length > 0 ? textures : null);
        return 0;
    }

    /// <summary>Distinct submesh materials (as JSON property bags) with how many submeshes use each.</summary>
    public static int Materials(string[] a)
    {
        var inputs = Inputs(a, out _, "*.lg", out var pak);
        using (pak)
            foreach (var (name, load) in inputs)
            {
                var m = SaberModel.Parse(load(), name);
                var groups = m.SubMeshes.GroupBy(s => System.Text.Json.JsonSerializer.Serialize(s.Material)).OrderByDescending(g => g.Count());
                Console.WriteLine($"== {name}: {groups.Count()} distinct materials over {m.SubMeshes.Count} submeshes (modes: {string.Join(",", m.SubMeshes.GroupBy(s => s.MaterialMode).Select(g => $"{g.Key}={g.Count()}"))})");
                foreach (var g in groups) Console.WriteLine($"{g.Count(),6} {g.Key}");
            }
        return 0;
    }

    public static int Info(string[] a)
    {
        var inputs = Inputs(a, out _, "", out var pak);
        using (pak)
            foreach (var (name, load) in inputs)
            {
                Console.WriteLine($"== {name}");
                try { Console.WriteLine(SaberModel.Parse(load(), name).Describe()); }
                catch (Exception ex) when (ex is InvalidDataException or NotSupportedException or EndOfStreamException or ArgumentOutOfRangeException or IndexOutOfRangeException)
                { Console.WriteLine($"FAILED {ex.GetType().Name}: {ex.Message}"); }
            }
        return 0;
    }
}
