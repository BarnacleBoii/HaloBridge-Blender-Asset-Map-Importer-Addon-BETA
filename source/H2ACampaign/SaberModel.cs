using System.Numerics;
using System.Text;
using System.Text.RegularExpressions;

namespace HaloBridge.H2ACampaign;

/// <summary>Little-endian reader over a byte array; offsets in Saber files are absolute within the entry.</summary>
sealed class R(byte[] b, int pos = 0)
{
    public readonly byte[] B = b;
    public int Pos = pos;
    public int Length => B.Length;
    void Need(int n) { if (Pos < 0 || Pos + n > B.Length) throw new EndOfStreamException($"Read of {n} bytes at 0x{Pos:X} past end 0x{B.Length:X}."); }
    public byte U8() { Need(1); return B[Pos++]; }
    public sbyte S8() => (sbyte)U8();
    public short I16() { Need(2); var v = BitConverter.ToInt16(B, Pos); Pos += 2; return v; }
    public ushort U16() { Need(2); var v = BitConverter.ToUInt16(B, Pos); Pos += 2; return v; }
    public int I32() { Need(4); var v = BitConverter.ToInt32(B, Pos); Pos += 4; return v; }
    public uint U32() { Need(4); var v = BitConverter.ToUInt32(B, Pos); Pos += 4; return v; }
    public ulong U64() { Need(8); var v = BitConverter.ToUInt64(B, Pos); Pos += 8; return v; }
    public float F32() { Need(4); var v = BitConverter.ToSingle(B, Pos); Pos += 4; return v; }
    public byte[] Bytes(int n) { Need(n); var v = B[Pos..(Pos + n)]; Pos += n; return v; }
    public string Str(int n)
    {
        if (n < 0 || n > 0x1000000) throw new InvalidDataException($"Bad string length {n} at 0x{Pos - 4:X}.");
        Need(n); var s = Encoding.UTF8.GetString(B, Pos, n); Pos += n; return s;
    }
    public string Str32() => Str(I32());
    public string Str16() => Str(I16());
    public string StrZ() { int e = Array.IndexOf(B, (byte)0, Pos); if (e < 0) throw new EndOfStreamException(); var s = Encoding.UTF8.GetString(B, Pos, e - Pos); Pos = e + 1; return s; }
    public Vector3 Vec3() => new(F32(), F32(), F32());
    public Matrix4x4 Mat4() => new(F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32(), F32());
    public bool[] Bits(int count) { var raw = Bytes((count + 7) / 8); return Enumerable.Range(0, count).Select(i => (raw[i / 8] >> (i % 8) & 1) != 0).ToArray(); }
    public uint Peek32() { Need(4); return BitConverter.ToUInt32(B, Pos); }
    public void Expect(uint sig, string name) { var v = U32(); if (v != sig) throw new InvalidDataException($"Expected {name} at 0x{Pos - 4:X}, found 0x{v:X8}."); }
    public int Find(uint sig, int from) { for (int i = Math.Max(0, from); i + 4 <= B.Length; i++) if (BitConverter.ToUInt32(B, i) == sig) return i; return -1; }
}

public sealed class SaberObject
{
    public int Index;
    public short Id = -1, ParentId = -1, NextId = -1, PrevId = -1, ChildId = -1, AnimNumber = -1;
    public string ReadName = "", ReadAffixes = "", UnkName = "", Name = "", Affixes = "";
    public Matrix4x4 MatrixLT = Matrix4x4.Identity, MatrixModel = Matrix4x4.Identity;
    public bool HasMatrixLT;
    public (uint SplitIndex, uint NumSplits, Vector3 Min, Vector3 Max)? GeomData;
    public string DisplayName => !string.IsNullOrEmpty(Name) ? Name : !string.IsNullOrEmpty(ReadName) ? ReadName : $"object_{Id}";
}

public sealed class GeometryBuffer
{
    public ushort FlagBits;
    public ulong Flags;
    public ushort ElementSize;
    public uint Length;
    public int Start;
    public bool Has(int bit) => (Flags >> bit & 1) != 0;
    public string Kind => Flags == 0 ? "face" : Has(Bit.VERT) ? "vertex" : Flags == 1ul << Bit.BONE ? "normal" : "interleaved";
}

public sealed class GeometryMesh
{
    public bool[] Flags = [];
    public List<(int BufferId, int SubOffset)> Buffers = [];
    public bool Flag(int bit) => bit < Flags.Length && Flags[bit];
}

public sealed class GeometrySubMesh
{
    public ushort VertexOffset, VertexCount, FaceOffset, FaceCount;
    public short NodeId = -1, SkinCompoundId = -1;
    public int MeshId;
    public Vector3? Position, Scale;
    public Dictionary<byte, short> UvScaling = [];
    public short[] BoneIds = [];
    public Dictionary<string, object?> Material = [];
    public string MaterialMode = "";
}

/// <summary>Bit numbers of the per-buffer element flags (names from the game's RTTI via LibSaber).</summary>
public static class Bit
{
    public const int VERT = 0, VERT_2D = 1, VERT_4D = 2, COMPRESSED_VERT = 3, WEIGHT1 = 4, WEIGHT2 = 5, WEIGHT3 = 6, WEIGHT4 = 7,
        INDEX = 8, BONE = 9, COMPRESSED_NORM = 10, NORM_IN_VERT4 = 11, TANG0 = 12, TANG4 = 16, COMPRESSED_TANG = 17,
        COLOR0 = 22, COLOR2 = 24, TEX0 = 25, TEX4 = 29, COMPRESSED_TEX0 = 30;
    public static readonly string[] Names =
    [
        "VERT", "VERT_2D", "VERT_4D", "COMPRESSED_VERT", "WEIGHT1", "WEIGHT2", "WEIGHT3", "WEIGHT4", "INDEX", "BONE",
        "COMPRESSED_NORM", "NORM_IN_VERT4", "TANG0", "TANG1", "TANG2", "TANG3", "TANG4", "COMPRESSED_TANG",
        "b18", "b19", "b20", "b21", "COLOR0", "COLOR1", "COLOR2", "TEX0", "TEX1", "TEX2", "TEX3", "TEX4",
        "CTEX0", "CTEX1", "CTEX2", "CTEX3", "CTEX4",
    ];
    public static string Describe(ulong f) =>
        f == 0 ? "(none)" : string.Join("|", Enumerable.Range(0, 64).Where(i => (f >> i & 1) != 0).Select(i => i < Names.Length ? Names[i] : $"b{i}"));
}

public sealed class LodRoot
{
    public List<uint> ObjectIds = [], MaxObjectLodIndices = [];
    public List<float> Distances = [];
}

public sealed class SaberModel
{
    public List<LodRoot> LodRoots = [];
    public List<(int ObjectId, int Index, bool IsLast)> LodDefinitions = [];

    /// <summary>
    /// Object ids that are not LOD0: in .lg LOD roots, ids at list positions >= MaxObjectLodIndices[0];
    /// in templates, LOD definitions with Index > 0. Children of a hidden object are hidden too.
    /// </summary>
    public HashSet<int> NonLod0ObjectIds()
    {
        var hidden = new HashSet<int>();
        foreach (var l in LodRoots)
            if (l.MaxObjectLodIndices.Count > 0)
                for (int i = (int)l.MaxObjectLodIndices[0]; i < l.ObjectIds.Count; i++) hidden.Add((int)l.ObjectIds[i]);
        foreach (var d in LodDefinitions) if (d.Index > 0) hidden.Add(d.ObjectId);
        foreach (var o in Objects)
        {
            // "<tpl>@SkinCompound_N" objects are merged copies of the per-part meshes (one per LOD level);
            // the parts themselves are kept, so the compounds would duplicate them (Index skips them too).
            if (o.DisplayName.Contains("@SkinCompound", StringComparison.OrdinalIgnoreCase)) hidden.Add(o.Id);
            // Per-part lower LODs are children named "<part>_LOD1".."_LOD9" (weapons) or "lod1", "lod2" (characters).
            if (Regex.IsMatch(o.DisplayName, @"_LOD[1-9]\b|^\.?lod[1-9]\b", RegexOptions.IgnoreCase)) hidden.Add(o.Id);
        }
        // Characters carry every armour variant ("_helmet_base", "_helmet_council", "_lights_honor"...) and
        // energy-shield shells ("_shield_default"...) around the whole body. Keep the default look: within a
        // part group that has a "_base"/"_default" member, its other variants are hidden; shields always are.
        // Bone objects ("_b_spine", "_gun_base" pivots) only qualify when they carry geometry themselves.
        var variants = Objects.Where(o => o.GeomData != null)
            .Select(o => (o, m: Regex.Match(o.DisplayName.TrimStart('.'), @"^_([a-z]+)_([a-z]+(?:_[a-z]+)*?)\d*(?:\.[a-z])?$", RegexOptions.IgnoreCase)))
            .Where(x => x.m.Success && !x.m.Groups[1].Value.Equals("b", StringComparison.OrdinalIgnoreCase)).ToList();
        foreach (var group in variants.GroupBy(x => x.m.Groups[1].Value.ToLowerInvariant()))
        {
            bool hasDefault = group.Any(x => x.m.Groups[2].Value is "base" or "default");
            foreach (var (o, m) in group)
                if (group.Key == "shield" || (hasDefault && m.Groups[2].Value is not ("base" or "default"))) hidden.Add(o.Id);
        }
        if (hidden.Count == 0) return hidden;
        bool changed = true;
        while (changed)
        {
            changed = false;
            foreach (var o in Objects)
                if (!hidden.Contains(o.Id) && o.ParentId >= 0 && hidden.Contains(o.ParentId)) { hidden.Add(o.Id); changed = true; }
        }
        return hidden;
    }

    /// <summary>A switchable part: region (variant group), permutation (the variant) and whether it is on by default.</summary>
    public readonly record struct PartChoice(string Region, string Permutation, bool Enabled);

    /// <summary>
    /// Sorts objects into HaloBridge region/permutation parts so variants can be toggled instead of hidden.
    /// Checked on the object and then its ancestors (children of a variant belong to it):
    ///   lower LODs ("_LOD1", "lod2", LOD definitions/roots past LOD0)  -> lod / lodN, off
    ///   "_&lt;group&gt;_&lt;variant&gt;" armour variants with geometry       -> group / variant, on for base/default
    ///                                                                  (or when the group has neither), shields off
    ///   damage / destroyed states                                    -> damage / name, off
    ///   everything else                                              -> body / default, on
    /// Skin compounds (merged duplicates of the parts) and engine helpers return null: never exported.
    /// </summary>
    public Dictionary<int, PartChoice?> ClassifyParts()
    {
        var byId = Objects.Where(o => o.Id >= 0).GroupBy(o => o.Id).ToDictionary(g => g.Key, g => g.First());
        var lodIndex = new Dictionary<int, int>();
        foreach (var l in LodRoots)
            for (int i = 0; i < l.ObjectIds.Count; i++)
            {
                int level = 0;
                while (level < l.MaxObjectLodIndices.Count && i >= l.MaxObjectLodIndices[level]) level++;
                if (level > 0) lodIndex[(int)l.ObjectIds[i]] = level;
            }
        foreach (var d in LodDefinitions) if (d.Index > 0) lodIndex[d.ObjectId] = d.Index;
        var variantRx = new Regex(@"^_([a-z]+)_([a-z]+(?:_[a-z]+)*?)\d*(?:\.[a-z])?$", RegexOptions.IgnoreCase);
        // "base", "default", "gun_base"... are a group's default look; "gun_destroyed", "gun_major"... damage states.
        static bool IsDefault(string variant) => Regex.IsMatch(variant, @"(^|_)(base|default)$", RegexOptions.IgnoreCase);
        static bool IsDamage(string variant) => Regex.IsMatch(variant, @"destroyed|damage|broken|(^|_)(major|medium|minor)$", RegexOptions.IgnoreCase);
        var groupDefaults = Objects.Where(o => o.GeomData != null).Select(o => variantRx.Match(o.DisplayName.TrimStart('.')))
            .Where(m => m.Success && !m.Groups[1].Value.Equals("b", StringComparison.OrdinalIgnoreCase))
            .GroupBy(m => m.Groups[1].Value.ToLowerInvariant())
            .ToDictionary(g => g.Key, g => g.Any(m => IsDefault(m.Groups[2].Value)));
        PartChoice? Own(SaberObject o)
        {
            var name = o.DisplayName;
            if (lodIndex.TryGetValue(o.Id, out var li)) return new("lod", "lod" + li, false);
            var lod = Regex.Match(name, @"_LOD([1-9])\b|^\.?lod([1-9])\b", RegexOptions.IgnoreCase);
            if (lod.Success) return new("lod", "lod" + (lod.Groups[1].Success ? lod.Groups[1].Value : lod.Groups[2].Value), false);
            var v = variantRx.Match(name.TrimStart('.'));
            if (v.Success && o.GeomData != null && !v.Groups[1].Value.Equals("b", StringComparison.OrdinalIgnoreCase))
            {
                var group = v.Groups[1].Value.ToLowerInvariant(); var variant = v.Groups[2].Value.ToLowerInvariant();
                bool on = group != "shield" && !IsDamage(variant) && (IsDefault(variant) || !groupDefaults.GetValueOrDefault(group));
                return new(group, variant, on);
            }
            if (Regex.IsMatch(name, "damage|destroyed", RegexOptions.IgnoreCase))
                return new("damage", Regex.Replace(name.Trim('.'), @"(\.[a-z])?$|_\$p\d*_?|#\d+", "").Trim('_', '.').ToLowerInvariant(), false);
            return null;
        }
        var result = new Dictionary<int, PartChoice?>();
        foreach (var o in Objects)
        {
            if (o.DisplayName.Contains("@SkinCompound", StringComparison.OrdinalIgnoreCase) || IsHelper(o)) { result[o.Id] = null; continue; }
            PartChoice? found = null;
            var seen = new HashSet<int>();
            for (var x = o; x != null && seen.Add(x.Id); x = x.ParentId >= 0 && byId.TryGetValue(x.ParentId, out var p) ? p : null)
            {
                if (x.DisplayName.Contains("@SkinCompound", StringComparison.OrdinalIgnoreCase) || IsHelper(x)) { found = null; goto excluded; }
                found = Own(x);
                if (found != null) break;
            }
            result[o.Id] = found ?? new PartChoice("body", "default", true);
            continue;
        excluded:
            result[o.Id] = null;
        }
        return result;
    }

    /// <summary>Engine helper geometry (occluders, shadow casters) that is not meant to be seen.</summary>
    public static bool IsHelper(SaberObject o) =>
        HelperRx.IsMatch(o.DisplayName) || HelperRx.IsMatch(o.UnkName.Split('\n')[0]);

    // Matches names like ".occl_o#0", ".mine_02_occl_o#0", "sun_ocluder", ".shadow_caster_o#0", ".shadowcaster_o#0".
    static readonly Regex HelperRx = new(@"occl|oclud|shadow_?caster|refl_box", RegexOptions.IgnoreCase);

    /// <summary>
    /// The untextured "red" placeholder material (no UV set, no lightmap): engine helper parts such as
    /// reflection-probe boxes and hidden door-frame pieces, not meant to be seen.
    /// </summary>
    public static bool IsPlaceholderMaterial(GeometrySubMesh s) =>
        s.Material.TryGetValue("layer0", out var l) && l is Dictionary<string, object?> layer &&
        layer.TryGetValue("texName", out var t) && t is string name && name.Equals("red", StringComparison.OrdinalIgnoreCase) &&
        !(s.Material.TryGetValue("shadingMtl_Tex", out var st) && st is string sts && sts.Length > 0);
    public string SourceName = "";
    public string Kind = "";           // "tpl" or "lg"
    public string Name = "", Affixes = "", PS = "";
    public List<string> SerStrings = [], TexList = [], InstMaterialInfo = [];
    public (Vector3 Min, Vector3 Max)? BoundingBox;
    public int GraphOffset, GraphType;
    public List<SaberObject> Objects = [];
    public List<GeometryBuffer> Buffers = [];
    public List<GeometryMesh> Meshes = [];
    public List<GeometrySubMesh> SubMeshes = [];
    public List<string> Notes = [];
    public byte[] Data = [];

    const uint SIG_1SER = 0x52455331, SIG_TPL = 0x006C7074, SIG_LG = 0xFF00676C, SIG_TPL1 = 0x314C5054, SIG_SCN1 = 0x314E4353, SIG_OGM1 = 0x314D474F;

    public static SaberModel Parse(byte[] data, string name)
    {
        var m = new SaberModel { SourceName = name, Data = data };
        var r = new R(data);
        r.Expect(SIG_1SER, "1SER");
        var kind = r.U32();
        m.Kind = kind == SIG_TPL ? "tpl" : kind == SIG_LG ? "lg" : throw new NotSupportedException($"Unsupported 1SER type 0x{kind:X8} (only tpl and lg).");
        ReadSerHeader(r, m);
        try
        {
            if (m.Kind == "tpl") ReadTpl1(r, m); else ReadScn1(r, m);
        }
        catch (Exception ex) when (ex is InvalidDataException or EndOfStreamException)
        {
            m.Notes.Add("header properties: " + ex.Message);
            r.Pos = -1;
        }
        if (r.Pos < 0 || r.Peek32() != SIG_OGM1)
        {
            int at = r.Find(SIG_OGM1, 0);
            if (at < 0) throw new InvalidDataException("No OGM1 geometry graph in this file.");
            m.Notes.Add($"OGM1 located by scanning (0x{at:X}).");
            r.Pos = at;
        }
        m.GraphOffset = r.Pos;
        ReadGraph(r, m);
        return m;
    }

    static void ReadSerHeader(R r, SaberModel m)
    {
        r.U64(); r.U64(); r.U64(); r.I32();
        r.Bytes(16); // GUID
        r.I32();
        int count = r.I32();
        r.I32();
        for (int i = 0; i < count; i++)
        {
            r.U16(); r.U8(); r.U8(); r.U64(); r.U64();
            m.SerStrings.Add(r.Str32());
        }
    }

    static void ReadTexList(R r, List<string> into)
    {
        uint count = r.U32(); r.U16(); r.U32();
        for (int i = 0; i < count; i++) into.Add(r.Str16());
        if (r.U16() != 0xFFFF) throw new InvalidDataException("TexList end marker missing.");
        r.U32();
    }

    static void ReadTpl1(R r, SaberModel m)
    {
        r.Expect(SIG_TPL1, "TPL1");
        var f = r.Bits(r.I32());
        bool F(int i) => i < f.Length && f[i];
        if (F(0)) m.Name = r.Str32();
        if (F(1)) r.Str32();                       // nameClass
        if (F(2)) { r.U16(); r.U32(); }            // state
        if (F(3)) m.Affixes = r.Str32();
        if (F(4)) m.PS = r.Str32();
        if (F(5)) ReadSkin(r);
        if (F(6) || F(7)) { m.Notes.Add("template has animation tracks; skipped by scanning for OGM1"); r.Pos = -1; return; }
        if (F(8)) m.BoundingBox = (r.Vec3(), r.Vec3());
        if (F(9)) // LOD definitions: (objectId, lod index, isLastLodUpToInfinity) per entry
        {
            int count = r.I32(); r.I32();
            var defs = Enumerable.Range(0, count).Select(_ => new int[] { -1, 0, 0 }).ToList();
            if (r.U8() != 0) foreach (var d in defs) d[0] = r.I16();
            if (r.U8() != 0) foreach (var d in defs) d[1] = r.U8();
            if (r.U8() != 0) foreach (var d in defs) d[2] = r.U8();
            m.LodDefinitions = defs.Select(d => (d[0], d[1], d[2] != 0)).ToList();
        }
        if (F(10)) ReadTexList(r, m.TexList);
        if (!F(11)) throw new InvalidDataException("Template has no geometry (GeometryMNG flag not set).");
    }

    static void ReadSkin(R r)
    {
        uint count = r.U32(); r.U16(); r.U8();
        ushort end = r.U16();
        if (end != 0xFFFF)
        {
            r.U32();
            for (int i = 0; i < count; i++) r.Mat4();
            end = r.U16();
        }
        if (end != 0xFFFF) throw new InvalidDataException("Bad skin property.");
        r.U32();
    }

    static void ReadScn1(R r, SaberModel m)
    {
        r.Expect(SIG_SCN1, "SCN1");
        var f = r.Bits((int)r.U32());
        if (f.Length > 0 && f[0]) ReadTexList(r, m.TexList);
        if (f.Length > 1 && f[1]) m.PS = r.Str32();
        if (f.Length > 2 && f[2])
        {
            uint count = r.U32(); r.U8();
            for (int i = 0; i < count; i++) { var a = r.Str32(); var b = r.Str32(); m.InstMaterialInfo.Add($"{a}: {b}"); }
        }
    }

    // ---- OGM1 geometry graph -------------------------------------------------------------

    static void ReadGraph(R r, SaberModel m)
    {
        r.Expect(SIG_OGM1, "OGM1");
        m.GraphType = r.U16(); r.U16(); r.U16();
        if (r.U8() != 0) ReadObjects(r, m);
        if (m.GraphType == 3)
        {
            int count = r.U8(); r.U8(); r.U8(); r.U8(); r.U8();
            for (int i = 0; i < count; i++) { r.U32(); m.Notes.Add("prop: " + r.Str32()); }
        }
        if (m.GraphType == 4) ReadGrassExtras(r, m);

        int bufferCount = 0, meshCount = 0, subMeshCount = 0;
        while (true)
        {
            ushort s = r.U16();
            switch (s)
            {
                case 0x0000:
                    {
                        int end = r.I32();
                        r.I16(); r.I32();
                        bufferCount = r.I32(); meshCount = r.I32(); subMeshCount = r.I32();
                        r.Pos = end;
                        break;
                    }
                case 0x0002: ReadBuffers(r, m, bufferCount); break;
                case 0x0003: ReadMeshes(r, m, meshCount); break;
                case 0x0004: ReadSubMeshes(r, m, subMeshCount); break;
                case 0xFFFF: r.Pos = r.I32(); return;
                default: throw new InvalidDataException($"Unknown geometry data sentinel 0x{s:X} at 0x{r.Pos - 2:X}.");
            }
        }
    }

    static void ReadGrassExtras(R r, SaberModel m)
    {
        int count = r.I32();
        if (r.U8() == 1) for (int i = 0; i < count; i++) { r.I32(); r.Str32(); }
        else r.Pos -= 5;
        uint roots = r.U32(); r.U32();
        var lods = Enumerable.Range(0, (int)roots).Select(_ => new LodRoot()).ToList();
        m.LodRoots = lods;
        if (r.U8() != 0) foreach (var l in lods) { int c = r.I32(); for (int i = 0; i < c; i++) l.ObjectIds.Add(r.U32()); }
        if (r.U8() != 0) foreach (var l in lods) { int c = r.I32(); for (int i = 0; i < c; i++) l.MaxObjectLodIndices.Add(r.U32()); }
        if (r.U8() != 0) foreach (var l in lods) { int c = r.I32(); r.U32(); if (r.U8() != 0) for (int i = 0; i < c; i++) l.Distances.Add(r.F32()); }
        if (r.U8() != 0) foreach (var l in lods) { r.Vec3(); r.Vec3(); }
        m.Notes.Add($"grass/LOD graph: {roots} lod roots");
    }

    static void ReadObjects(R r, SaberModel m)
    {
        int n = r.I16(); r.U16(); int props = r.U16(); r.U16();
        var objs = Enumerable.Range(0, n).Select(i => new SaberObject { Index = i }).ToList();
        m.Objects = objs;
        bool P(int i) => props > i && r.U8() != 0;
        if (P(0)) foreach (var o in objs) o.Id = r.I16();
        if (P(1)) foreach (var o in objs) o.ReadName = r.Str32();
        if (P(2)) foreach (var o in objs) { r.U16(); r.U16(); r.U16(); r.U8(); }
        if (P(3)) foreach (var o in objs) o.ParentId = r.I16();
        if (P(4)) foreach (var o in objs) o.NextId = r.I16();
        if (P(5)) foreach (var o in objs) o.PrevId = r.I16();
        if (P(6)) foreach (var o in objs) o.ChildId = r.I16();
        if (P(7)) foreach (var o in objs) o.AnimNumber = r.I16();
        if (P(8)) foreach (var o in objs) o.ReadAffixes = r.Str32();
        if (P(9)) foreach (var o in objs) { o.MatrixLT = r.Mat4(); o.HasMatrixLT = true; }
        if (P(10)) foreach (var o in objs) o.MatrixModel = r.Mat4();
        if (P(11))
        {
            var has = r.Bits(n);
            for (int i = 0; i < n; i++)
                if (has[i])
                {
                    uint a = r.U32(); byte b = r.U8();
                    if (a != 3 || b != 7) throw new InvalidDataException($"Unexpected objGEOM_UNSHARED header {a}/{b} at 0x{r.Pos - 5:X}.");
                    objs[i].GeomData = (r.U32(), r.U32(), r.Vec3(), r.Vec3());
                }
        }
        if (P(12)) foreach (var o in objs) o.UnkName = r.Str32();
        if (P(13)) r.Pos += 60 * n; // OBB
        if (P(14)) foreach (var o in objs) o.Name = r.Str16();
        if (P(15)) foreach (var o in objs) o.Affixes = r.Str16();
        if (props > 16) throw new NotSupportedException($"Object list has {props} properties (max known 16).");
    }

    static void ReadBuffers(R r, SaberModel m, int count)
    {
        int end = r.I32();
        var bufs = Enumerable.Range(0, count).Select(_ => new GeometryBuffer()).ToList();
        m.Buffers = bufs;
        while (r.Pos < end)
        {
            short id = r.I16(); int blockEnd = r.I32();
            switch (id)
            {
                case 0: foreach (var b in bufs) { b.FlagBits = r.U16(); b.Flags = r.U64(); } break;
                case 1: foreach (var b in bufs) b.ElementSize = r.U16(); break;
                case 2: foreach (var b in bufs) b.Length = r.U32(); break;
                case 3: foreach (var b in bufs) { b.Start = r.Pos; r.Pos += (int)b.Length; } break;
                default: m.Notes.Add($"buffers: unknown block 0x{id:X}"); break;
            }
            r.Pos = blockEnd;
        }
        r.Pos = end;
    }

    static void ReadMeshes(R r, SaberModel m, int count)
    {
        int end = r.I32();
        var meshes = Enumerable.Range(0, count).Select(_ => new GeometryMesh()).ToList();
        m.Meshes = meshes;
        while (r.Pos < end)
        {
            short id = r.I16(); int blockEnd = r.I32();
            switch (id)
            {
                case 0: foreach (var x in meshes) x.Flags = r.Bits(r.I16()); break;
                case 2:
                    foreach (var x in meshes)
                    {
                        int c = r.U8();
                        for (int i = 0; i < c; i++) x.Buffers.Add((r.I32(), r.I32()));
                    }
                    break;
                default: m.Notes.Add($"meshes: unknown block 0x{id:X}"); break;
            }
            r.Pos = blockEnd;
        }
        r.Pos = end;
    }

    static void SkipRotatingFloatPairs(R r)
    {
        uint flags = r.U32();
        for (int i = 0; i < 32; i++)
        {
            if ((flags & 1) != 0) { r.F32(); r.F32(); }
            flags = flags << 1 | flags >> 31;
        }
    }

    static void ReadSubMeshes(R r, SaberModel m, int count)
    {
        int end = r.I32();
        var subs = Enumerable.Range(0, count).Select(_ => new GeometrySubMesh()).ToList();
        m.SubMeshes = subs;
        while (r.Pos < end)
        {
            short id = r.I16(); int blockEnd = r.I32();
            try
            {
                switch (id)
                {
                    case 0:
                        if (count == 0) break;
                        bool extra = (blockEnd - r.Pos) / count > 12;
                        foreach (var s in subs)
                        {
                            s.VertexOffset = r.U16(); s.VertexCount = r.U16(); s.FaceOffset = r.U16(); s.FaceCount = r.U16();
                            s.NodeId = r.I16(); s.SkinCompoundId = r.I16();
                            if (extra) SkipRotatingFloatPairs(r);
                        }
                        break;
                    case 1: foreach (var s in subs) s.MeshId = r.I32(); break;
                    case 3:
                        foreach (var s in subs)
                            if (m.Meshes[s.MeshId].Flag(9)) { int c = r.U8(); s.BoneIds = Enumerable.Range(0, c).Select(_ => r.I16()).ToArray(); }
                        break;
                    case 4:
                        foreach (var s in subs)
                            if (m.Meshes[s.MeshId].Flag(30)) { int c = r.U8(); for (int i = 0; i < c; i++) { var k = r.U8(); s.UvScaling[k] = r.I16(); } }
                        break;
                    case 5:
                        foreach (var s in subs)
                            if (m.Meshes[s.MeshId].Flag(3)) { s.Position = new(r.I16(), r.I16(), r.I16()); s.Scale = new(r.I16(), r.I16(), r.I16()); }
                        break;
                    case 6:
                        foreach (var s in subs) { r.U16(); s.MaterialMode = "string"; s.Material = ParseMaterialText(r.Str32()); }
                        break;
                    case 7:
                        foreach (var s in subs) { r.U16(); s.MaterialMode = "static"; s.Material = ReadBinaryObject(r, staticNames: true); }
                        break;
                    case 8:
                        foreach (var s in subs) { r.U16(); s.MaterialMode = "dynamic"; s.Material = ReadBinaryObject(r, staticNames: false); }
                        break;
                    case 2: break; // unknown per-submesh block (LibSaber "Unk_02"); skipped via its end offset
                    default: m.Notes.Add($"submeshes: unknown block 0x{id:X}"); break;
                }
            }
            catch (Exception ex) when (ex is InvalidDataException or EndOfStreamException or ArgumentOutOfRangeException)
            {
                m.Notes.Add($"submeshes: block 0x{id:X} not fully parsed ({ex.Message})");
            }
            r.Pos = blockEnd;
        }
        r.Pos = end;
    }

    // Saber "scripting" property bags used for materials. Types: 1 int, 2 float, 3 bool, 4 string, 6 array, 7 class.
    static Dictionary<string, object?> ReadBinaryObject(R r, bool staticNames)
    {
        var d = new Dictionary<string, object?>();
        uint n = r.U32();
        if (n > 4096) throw new InvalidDataException($"Implausible material property count {n}.");
        for (int i = 0; i < n; i++)
        {
            string name = staticNames ? r.StrZ() : r.Str32();
            if (staticNames) r.U32();
            d[name] = ReadValue(r, r.U32(), staticNames);
        }
        return d;
    }

    static object? ReadValue(R r, uint type, bool staticNames) => type switch
    {
        1 => r.I32(),
        2 => r.F32(),
        3 => r.U8() != 0,
        4 => r.Str32(),
        6 => Enumerable.Range(0, (int)r.U32()).Select(_ => ReadValue(r, r.U32(), staticNames)).ToArray(),
        7 => ReadBinaryObject(r, staticNames),
        _ => throw new InvalidDataException($"Unknown material value type {type} at 0x{r.Pos - 4:X}."),
    };

    static Dictionary<string, object?> ParseMaterialText(string text)
    {
        var d = new Dictionary<string, object?> { ["_text"] = text };
        foreach (Match mt in Regex.Matches(text, @"(\w+)\s*=\s*\{[^{}]*?texName\s*=\s*""([^""]*)""", RegexOptions.Singleline))
            d[mt.Groups[1].Value] = new Dictionary<string, object?> { ["texName"] = mt.Groups[2].Value };
        var tex = Regex.Match(text, @"shadingMtl_Tex\s*=\s*""([^""]*)""");
        if (tex.Success) d["shadingMtl_Tex"] = tex.Groups[1].Value;
        return d;
    }

    /// <summary>Texture names a submesh material references (layer0..3 texName, shadingMtl_Tex), first = main diffuse.</summary>
    public static List<string> MaterialTextures(GeometrySubMesh s)
    {
        var list = new List<string>();
        foreach (var key in new[] { "layer0", "layer1", "layer2", "layer3" })
            if (s.Material.TryGetValue(key, out var v) && v is Dictionary<string, object?> layer && layer.TryGetValue("texName", out var t) && t is string ts && ts.Length > 0)
                list.Add(ts);
        if (s.Material.TryGetValue("shadingMtl_Tex", out var st) && st is string sts && sts.Length > 0) list.Add(sts);
        return list.Distinct().ToList();
    }

    // ---- Vertex decoding --------------------------------------------------------------------

    /// <summary>
    /// The object owning a submesh: the object whose objGEOM_UNSHARED split range [SplitIndex, +NumSplits)
    /// contains the submesh index (verified on crate_packing__h: its ".render.g" object carries the 0.32 scale
    /// that brings vertices inside the template bounding box). Falls back to NodeId.
    /// </summary>
    public SaberObject? ObjectFor(GeometrySubMesh s)
    {
        int index = SubMeshes.IndexOf(s);
        return Objects.FirstOrDefault(o => o.GeomData is { } g && index >= g.SplitIndex && index < g.SplitIndex + g.NumSplits)
            ?? Objects.FirstOrDefault(o => o.Id == s.NodeId);
    }

    /// <summary>Size in bytes that the known vertex flags account for (for checking against ElementSize).</summary>
    public static int ExpectedElementSize(GeometryBuffer b)
    {
        if (b.Kind == "face") return 6;
        if (b.Kind == "normal") return 4;
        if (b.Kind == "vertex")
        {
            int n = b.Has(Bit.COMPRESSED_VERT) ? 6 : 12;
            if (b.Has(Bit.NORM_IN_VERT4)) n += b.Has(Bit.COMPRESSED_VERT) ? 2 : 4;
            else if (b.Has(Bit.COMPRESSED_NORM) && !b.Has(Bit.COMPRESSED_VERT)) n += 12;
            for (int w = Bit.WEIGHT1; w <= Bit.WEIGHT4; w++) if (b.Has(w)) n += 1;
            if (b.Has(Bit.INDEX)) n += 4;
            return n;
        }
        int size = 0;
        for (int t = Bit.TANG0; t <= Bit.TANG4; t++) if (b.Has(t)) size += 4;
        for (int c = Bit.COLOR0; c <= Bit.COLOR2; c++) if (b.Has(c)) size += 4;
        for (int t = 0; t < 5; t++) if (b.Has(Bit.TEX0 + t)) size += b.Has(Bit.COMPRESSED_TEX0 + t) ? 4 : 8;
        return size;
    }

    public sealed class MeshData
    {
        public List<Vector3> Positions = [];
        public List<Vector3> Normals = [];
        public List<Vector2> Uvs = [];
        public List<(int A, int B, int C)> Faces = [];
    }

    /// <summary>Builds one submesh: vertices [VertexOffset, +VertexCount), faces [FaceOffset, +FaceCount) of its mesh's buffers.</summary>
    public MeshData BuildSubMesh(GeometrySubMesh s, bool applyTransform, int uvSet = 0)
    {
        uvSet = Math.Clamp(uvSet, 0, 4);
        var md = new MeshData();
        var mesh = Meshes[s.MeshId];
        var obj = ObjectFor(s);
        var xf = applyTransform && obj != null ? obj.MatrixLT : Matrix4x4.Identity;
        var pos = s.Position ?? Vector3.Zero;
        var scale = s.Scale ?? Vector3.One;
        foreach (var (bufferId, subOffset) in mesh.Buffers)
        {
            var b = Buffers[bufferId];
            int stride = b.ElementSize;
            int baseOff = b.Start + subOffset;
            switch (b.Kind)
            {
                case "vertex":
                    for (int i = 0; i < s.VertexCount; i++)
                    {
                        var r = new R(Data, baseOff + (s.VertexOffset + i) * stride);
                        Vector3 p; Vector3? n = null;
                        if (b.Has(Bit.COMPRESSED_VERT))
                        {
                            p = new Vector3(r.I16() / 32767f, r.I16() / 32767f, r.I16() / 32767f) * scale + pos;
                            if (b.Has(Bit.NORM_IN_VERT4)) n = NormalFromInt16(r.I16());
                        }
                        else
                        {
                            p = r.Vec3();
                            if (b.Has(Bit.NORM_IN_VERT4)) n = NormalFromFloat(r.F32());
                            else if (b.Has(Bit.COMPRESSED_NORM) && stride >= 24) n = r.Vec3();
                        }
                        md.Positions.Add(Vector3.Transform(p, xf));
                        if (n.HasValue) md.Normals.Add(Vector3.Normalize(Vector3.TransformNormal(n.Value, xf)));
                    }
                    break;
                case "normal":
                    // Separate normal stream (flags = BONE only, 4 bytes): UNORM8 x,y,z (+ unused w), n = 2*v - 1.
                    for (int i = 0; i < s.VertexCount; i++)
                    {
                        int o = baseOff + (s.VertexOffset + i) * stride;
                        var n = new Vector3(Data[o] / 255f * 2 - 1, Data[o + 1] / 255f * 2 - 1, Data[o + 2] / 255f * 2 - 1);
                        md.Normals.Add(Vector3.Normalize(Vector3.TransformNormal(n, xf)));
                    }
                    break;
                case "interleaved":
                    {
                        if (!b.Has(Bit.TEX0 + uvSet)) break;
                        int uvOff = 0;
                        for (int t = Bit.TANG0; t <= Bit.TANG4; t++) if (b.Has(t)) uvOff += 4;
                        for (int c = Bit.COLOR0; c <= Bit.COLOR2; c++) if (b.Has(c)) uvOff += 4;
                        for (int t = 0; t < uvSet; t++) if (b.Has(Bit.TEX0 + t)) uvOff += b.Has(Bit.COMPRESSED_TEX0 + t) ? 4 : 8;
                        bool comp = b.Has(Bit.COMPRESSED_TEX0 + uvSet);
                        float uvScale = s.UvScaling.TryGetValue((byte)uvSet, out var sc) ? sc : 1;
                        for (int i = 0; i < s.VertexCount; i++)
                        {
                            var r = new R(Data, baseOff + (s.VertexOffset + i) * stride + uvOff);
                            float u = comp ? r.I16() / 32767f : r.F32();
                            float v = comp ? r.I16() / 32767f : r.F32();
                            md.Uvs.Add(new Vector2(u * uvScale, 1 - v * uvScale));
                        }
                        break;
                    }
                case "face":
                    for (int i = 0; i < s.FaceCount; i++)
                    {
                        var r = new R(Data, baseOff + (s.FaceOffset + i) * stride);
                        int a = r.U16() - s.VertexOffset, bb = r.U16() - s.VertexOffset, c = r.U16() - s.VertexOffset;
                        if ((uint)a >= s.VertexCount || (uint)bb >= s.VertexCount || (uint)c >= s.VertexCount)
                            throw new InvalidDataException($"Face index outside submesh vertex range (mesh {s.MeshId}).");
                        // Degenerate triangles (a repeated vertex; strip joins) have no area. Blender's
                        // custom-normals setter crashes on them (battle_rifle__h has 10), so they are dropped.
                        if (a == bb || bb == c || a == c) continue;
                        md.Faces.Add((a, bb, c));
                    }
                    break;
            }
        }
        if (md.Uvs.Count != md.Positions.Count) md.Uvs.Clear();
        if (md.Normals.Count != md.Positions.Count) md.Normals.Clear();
        return md;
    }

    // Normal packing from the game's common_input.vsh (documented by LibSaber).
    static Vector3 NormalFromInt16(short w)
    {
        float a = Math.Abs((int)w);
        float x = (-1f + 2f * Frac(a / 181f)) * (181f / 179f);
        float z = (-1f + 2f * Frac(a / 181f / 181f)) * (181f / 180f);
        float y = Math.Sign(w) * MathF.Sqrt(Math.Clamp(1f - x * x - z * z, 0, 1));
        return new Vector3(x, y, z);
    }

    static Vector3 NormalFromFloat(float w) =>
        new(-1f + 2f * Frac(w / 256f), -1f + 2f * Frac(w / 65536f), -1f + 2f * Frac(w / 16777216f));

    static float Frac(float v) => v - MathF.Floor(v);

    // ---- Diagnostics --------------------------------------------------------------------------

    public string Describe()
    {
        var sb = new StringBuilder();
        sb.AppendLine($"kind={Kind} name='{Name}' graphType={GraphType} OGM1@0x{GraphOffset:X} size={Data.Length}");
        if (SerStrings.Count > 0) sb.AppendLine("1SER strings: " + string.Join(", ", SerStrings));
        if (BoundingBox is { } bb) sb.AppendLine($"bbox {bb.Min} .. {bb.Max}");
        if (TexList.Count > 0) sb.AppendLine($"texList[{TexList.Count}]: " + string.Join(", ", TexList.Take(20)) + (TexList.Count > 20 ? ", ..." : ""));
        if (PS.Length > 0) sb.AppendLine("ps: " + PS.Replace("\n", " | ").Trim());
        if (InstMaterialInfo.Count > 0) sb.AppendLine($"instMaterialInfo[{InstMaterialInfo.Count}]: " + string.Join(" ; ", InstMaterialInfo.Take(5)));
        foreach (var n in Notes.Take(20)) sb.AppendLine("note: " + n);
        sb.AppendLine($"objects={Objects.Count} buffers={Buffers.Count} meshes={Meshes.Count} submeshes={SubMeshes.Count}");
        if (LodDefinitions.Count > 0)
            sb.AppendLine("lodDefinitions (objId:index:last): " + string.Join(" ", LodDefinitions.Select(d => $"{d.ObjectId}:{d.Index}:{(d.IsLast ? 1 : 0)}")));
        foreach (var l in LodRoots.Take(8))
            sb.AppendLine($"  lodRoot objects=[{string.Join(",", l.ObjectIds.Take(12))}{(l.ObjectIds.Count > 12 ? ",..." : "")}] maxLod=[{string.Join(",", l.MaxObjectLodIndices.Take(12))}] dist=[{string.Join(",", l.Distances.Select(d => d.ToString("0.#")))}]" +
                $" names=[{string.Join(", ", l.ObjectIds.Take(4).Select(id => Objects.FirstOrDefault(o => o.Id == id)?.DisplayName ?? "?"))}]");
        var kinds = Objects.GroupBy(o => Regex.Replace(o.DisplayName, @"[#\d]+|^\.|\.\w$", "")).OrderByDescending(g => g.Count()).Take(15);
        sb.AppendLine("object name kinds: " + string.Join(", ", kinds.Select(g => $"{g.Key}={g.Count()}")));
        foreach (var o in Objects.Where(o => o.GeomData != null).OrderByDescending(o => (o.GeomData!.Value.Max - o.GeomData.Value.Min).Length()).Take(5))
            sb.AppendLine($"  largest: '{o.DisplayName}' size={(o.GeomData!.Value.Max - o.GeomData.Value.Min)} path='{o.UnkName.Split('\n')[0]}'");
        foreach (var o in Objects.Take(40))
        {
            var t = o.MatrixLT.Translation;
            var mm = o.MatrixModel;
            sb.AppendLine($"  obj[{o.Index}] id={o.Id} parent={o.ParentId} name='{o.DisplayName}' unkName='{o.UnkName}' LT.T=({t.X:0.###},{t.Y:0.###},{t.Z:0.###}) LT.diag=({o.MatrixLT.M11:0.###},{o.MatrixLT.M22:0.###},{o.MatrixLT.M33:0.###}) Model.T=({mm.M41:0.###},{mm.M42:0.###},{mm.M43:0.###}) Model.diag=({mm.M11:0.###},{mm.M22:0.###},{mm.M33:0.###}){(o.GeomData is { } g ? $" geom split={g.SplitIndex}+{g.NumSplits}" : "")}");
        }
        if (Objects.Count > 40) sb.AppendLine($"  ... {Objects.Count - 40} more objects");
        for (int i = 0; i < Buffers.Count; i++)
        {
            var b = Buffers[i];
            int exp = ExpectedElementSize(b);
            sb.AppendLine($"  buf[{i}] {b.Kind,-11} stride={b.ElementSize} known={exp}{(exp != b.ElementSize ? " (MISMATCH)" : "")} len={b.Length} @0x{b.Start:X} flags={Bit.Describe(b.Flags)}");
        }
        for (int i = 0; i < Math.Min(Meshes.Count, 40); i++)
        {
            var x = Meshes[i];
            var set = Enumerable.Range(0, x.Flags.Length).Where(k => x.Flags[k]);
            sb.AppendLine($"  mesh[{i}] buffers=[{string.Join(", ", x.Buffers.Select(bf => $"{bf.BufferId}+{bf.SubOffset}"))}] flags={{{string.Join(",", set)}}}");
        }
        for (int i = 0; i < Math.Min(SubMeshes.Count, 60); i++)
        {
            var s = SubMeshes[i];
            sb.AppendLine($"  sub[{i}] mesh={s.MeshId} node={s.NodeId} v={s.VertexOffset}+{s.VertexCount} f={s.FaceOffset}+{s.FaceCount}" +
                (s.Position is { } p ? $" pos={p} scale={s.Scale}" : "") + (s.UvScaling.Count > 0 ? $" uvScale={string.Join(",", s.UvScaling.Select(kv => $"{kv.Key}:{kv.Value}"))}" : "") +
                $" mat({s.MaterialMode})=[{string.Join(", ", MaterialTextures(s))}]");
        }
        if (SubMeshes.Count > 60) sb.AppendLine($"  ... {SubMeshes.Count - 60} more submeshes");
        // Sanity check: decoded vertex normals should point the same way as the triangle winding normals.
        long agree = 0, total = 0, withNormals = 0;
        foreach (var s in SubMeshes.Take(200))
        {
            try
            {
                var md = BuildSubMesh(s, true);
                if (md.Normals.Count == 0) continue;
                withNormals++;
                foreach (var (a, b, c) in md.Faces)
                {
                    var fn = Vector3.Cross(md.Positions[b] - md.Positions[a], md.Positions[c] - md.Positions[a]);
                    if (fn.LengthSquared() < 1e-20f) continue;
                    total++;
                    if (Vector3.Dot(fn, md.Normals[a] + md.Normals[b] + md.Normals[c]) > 0) agree++;
                }
            }
            catch (Exception ex) when (ex is InvalidDataException or EndOfStreamException or ArgumentOutOfRangeException) { }
        }
        if (total > 0) sb.AppendLine($"normal check: {withNormals} submeshes with normals, {100.0 * agree / total:0.0}% of {total} faces agree with CCW winding");
        return sb.ToString();
    }
}

static class ObjWriter
{
    /// <summary>Writes an OBJ (+ .mtl naming the referenced textures as PNGs). Returns a stats string.</summary>
    public static string Write(SaberModel m, string path, bool allLods = false, bool helpers = false, bool applyTransform = true)
    {
        var mtlPath = Path.ChangeExtension(path, ".mtl");
        var materials = new Dictionary<string, string>();
        int vBase = 1, faces = 0, verts = 0, skipped = 0, filtered = 0;
        var nonLod0 = allLods ? [] : m.NonLod0ObjectIds();
        using var w = new StreamWriter(path, false, new UTF8Encoding(false));
        w.WriteLine($"# {m.SourceName} exported by HaloBridge.H2ACampaign (Halo 2 Anniversary Saber3D {m.Kind})");
        w.WriteLine($"mtllib {Path.GetFileName(mtlPath)}");
        for (int i = 0; i < m.SubMeshes.Count; i++)
        {
            var s = m.SubMeshes[i];
            var owner = m.ObjectFor(s);
            if (owner != null && (nonLod0.Contains(owner.Id) || (!helpers && SaberModel.IsHelper(owner)))) { filtered++; continue; }
            SaberModel.MeshData md;
            try { md = m.BuildSubMesh(s, applyTransform); }
            catch (Exception ex) when (ex is InvalidDataException or EndOfStreamException or ArgumentOutOfRangeException)
            {
                w.WriteLine($"# submesh {i} skipped: {ex.Message}");
                skipped++;
                continue;
            }
            if (md.Faces.Count == 0) continue;
            var obj = m.ObjectFor(s);
            var tex = SaberModel.MaterialTextures(s);
            var mat = tex.Count > 0 ? Sanitize(Path.GetFileNameWithoutExtension(tex[0])) : "default";
            materials.TryAdd(mat, tex.Count > 0 ? tex[0] : "");
            w.WriteLine($"o {Sanitize(obj?.DisplayName ?? "mesh")}_{i}");
            foreach (var p in md.Positions) w.WriteLine($"v {p.X:0.######} {p.Y:0.######} {p.Z:0.######}");
            foreach (var t in md.Uvs) w.WriteLine($"vt {t.X:0.######} {t.Y:0.######}");
            foreach (var n in md.Normals) w.WriteLine($"vn {n.X:0.####} {n.Y:0.####} {n.Z:0.####}");
            w.WriteLine($"usemtl {mat}");
            bool hasT = md.Uvs.Count > 0, hasN = md.Normals.Count > 0;
            foreach (var (a, b, c) in md.Faces)
            {
                string V(int k) { int x = k + vBase; return hasT && hasN ? $"{x}/{x}/{x}" : hasT ? $"{x}/{x}" : hasN ? $"{x}//{x}" : $"{x}"; }
                w.WriteLine($"f {V(a)} {V(b)} {V(c)}");
            }
            vBase += md.Positions.Count;
            verts += md.Positions.Count;
            faces += md.Faces.Count;
        }
        using (var mw = new StreamWriter(mtlPath, false, new UTF8Encoding(false)))
            foreach (var (name, tex) in materials)
            {
                mw.WriteLine($"newmtl {name}");
                mw.WriteLine("Kd 0.8 0.8 0.8");
                if (tex.Length > 0) mw.WriteLine($"map_Kd {Path.GetFileNameWithoutExtension(tex)}.png");
                mw.WriteLine();
            }
        return $"vertices={verts} faces={faces} submeshes={m.SubMeshes.Count - skipped - filtered}/{m.SubMeshes.Count} (filtered {filtered} LOD/helper, failed {skipped}) materials={materials.Count}";
    }

    static string Sanitize(string s) => Regex.Replace(s, @"[^\w\.\-]", "_");
}
