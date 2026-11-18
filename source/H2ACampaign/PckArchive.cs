using System.IO.Compression;
using System.Text;

namespace HaloBridge.H2ACampaign;

/// <summary>
/// Random-access view of the uncompressed bytes of a Saber3D (H2A) .pck file.
/// The file starts with a 0x600000-byte chunk table: int32 chunkCount, int32 mode
/// (0 = zlib-compressed), then chunkCount int64 file offsets. Each chunk holds 0x8000
/// uncompressed bytes (the last may be shorter) and is an independent zlib stream.
/// </summary>
public sealed class ChunkedFile : IDisposable
{
    public const int ChunkSize = 0x8000;
    public const int TableSize = 0x600000;

    readonly FileStream _fs;
    readonly long[] _starts;
    readonly int _lastChunkLength;
    int _cachedIndex = -1;
    readonly byte[] _cache = new byte[ChunkSize];
    int _cachedLength;

    public bool IsCompressed { get; }
    public int ChunkCount => _starts.Length;
    public long Length { get; }

    public ChunkedFile(string path)
    {
        _fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16);
        using var br = new BinaryReader(_fs, Encoding.ASCII, leaveOpen: true);
        int count = br.ReadInt32();
        IsCompressed = br.ReadInt32() == 0;
        if (count <= 0 || count > (TableSize - 8) / 8) throw new InvalidDataException("Not a Saber3D .pck (bad chunk count).");
        _starts = new long[count];
        for (int i = 0; i < count; i++) _starts[i] = br.ReadInt64();
        _lastChunkLength = IsCompressed ? DecompressChunk(count - 1, _cache) : (int)Math.Min(ChunkSize, _fs.Length - _starts[^1]);
        _cachedIndex = IsCompressed ? count - 1 : -1;
        _cachedLength = _lastChunkLength;
        Length = (long)(count - 1) * ChunkSize + _lastChunkLength;
    }

    int DecompressChunk(int index, byte[] dst)
    {
        _fs.Position = _starts[index];
        using var z = new ZLibStream(_fs, CompressionMode.Decompress, leaveOpen: true);
        int total = 0, n;
        while (total < dst.Length && (n = z.Read(dst, total, dst.Length - total)) > 0) total += n;
        return total;
    }

    public void Read(long position, Span<byte> dst)
    {
        if (position < 0 || position + dst.Length > Length) throw new ArgumentOutOfRangeException(nameof(position));
        while (dst.Length > 0)
        {
            int ci = (int)(position / ChunkSize);
            int within = (int)(position % ChunkSize);
            if (!IsCompressed)
            {
                int len = ci == ChunkCount - 1 ? _lastChunkLength : ChunkSize;
                int take = Math.Min(len - within, dst.Length);
                _fs.Position = _starts[ci] + within;
                _fs.ReadExactly(dst[..take]);
                dst = dst[take..]; position += take;
                continue;
            }
            if (ci != _cachedIndex) { _cachedLength = DecompressChunk(ci, _cache); _cachedIndex = ci; }
            int n = Math.Min(_cachedLength - within, dst.Length);
            if (n <= 0) throw new InvalidDataException($"Chunk {ci} is shorter than expected.");
            _cache.AsSpan(within, n).CopyTo(dst);
            dst = dst[n..]; position += n;
        }
    }

    public byte[] Read(long position, int length)
    {
        var b = new byte[length];
        Read(position, b);
        return b;
    }

    public void Dispose() => _fs.Dispose();
}

public sealed class PckEntry
{
    public required string RawName { get; init; }
    public required long Offset { get; init; }   // absolute offset in the uncompressed stream
    public required int Size { get; init; }
    public required int Depth { get; init; }
    public PckEntry? Parent { get; init; }
    public List<PckEntry> Children { get; } = [];
    public bool IsContainer => Children.Count > 0;

    /// <summary>Category prefix such as "textures", "database", "scene", "tpl" (empty if none).</summary>
    public string Category
    {
        get
        {
            int a = RawName.IndexOf('<'), b = RawName.IndexOf('>');
            return a >= 0 && b > a ? RawName[(a + 1)..b] : "";
        }
    }

    /// <summary>Name without the category prefix, with '\' separators, e.g. "tpl\sm_geom_00011.tpl".</summary>
    public string Path
    {
        get
        {
            var n = RawName;
            int b = n.IndexOf('>');
            if (b >= 0) n = n[(b + 1)..];
            return n.TrimStart(':', '\\', '/').Replace('/', '\\');
        }
    }

    public string FileName => System.IO.Path.GetFileName(Path);
    public string Extension => System.IO.Path.GetExtension(Path).ToLowerInvariant();

    public override string ToString() => RawName;
}

/// <summary>
/// Reads the "1SERpak" directory inside the uncompressed .pck stream. Entries whose data
/// starts with "1SERpak\0" are nested containers and are expanded recursively, with their
/// child offsets relative to the nested container's start.
/// </summary>
public sealed class PckArchive : IDisposable
{
    public const ulong Magic1SERpak = 0x006B617052455331; // "1SERpak\0"
    public const int PakHeaderSize = 0x45;

    public ChunkedFile Data { get; }
    public string FilePath { get; }
    public List<PckEntry> Roots { get; } = [];
    public List<PckEntry> All { get; } = [];
    public byte[] RootHeader { get; private set; } = [];
    public int RootUnknown { get; private set; }

    public PckArchive(string path)
    {
        FilePath = path;
        Data = new ChunkedFile(path);
        ReadDirectory(0, 0, null, Roots);
    }

    void ReadDirectory(long baseOffset, int depth, PckEntry? parent, List<PckEntry> into)
    {
        var header = Data.Read(baseOffset, PakHeaderSize);
        if (BitConverter.ToUInt64(header, 0) != Magic1SERpak) throw new InvalidDataException($"No 1SERpak header at 0x{baseOffset:X}.");
        if (depth == 0) RootHeader = header;
        long pos = baseOffset + PakHeaderSize;
        int ReadI32() { var v = BitConverter.ToInt32(Data.Read(pos, 4)); pos += 4; return v; }
        int count = ReadI32();
        int unk = ReadI32();
        if (depth == 0) RootUnknown = unk;
        pos += 1; // 0x00 delimiter
        if (count < 0 || count > 1_000_000) throw new InvalidDataException($"Bad entry count {count} at 0x{baseOffset:X}.");

        var names = new string[count];
        for (int i = 0; i < count; i++)
        {
            int len = ReadI32();
            names[i] = Encoding.UTF8.GetString(Data.Read(pos, len));
            pos += len;
        }
        pos += 1;
        var offsets = new long[count];
        var raw = Data.Read(pos, count * 8); pos += count * 8;
        for (int i = 0; i < count; i++) offsets[i] = BitConverter.ToInt64(raw, i * 8);
        pos += 1;
        var sizes = new int[count];
        raw = Data.Read(pos, count * 4);
        for (int i = 0; i < count; i++) sizes[i] = BitConverter.ToInt32(raw, i * 4);

        for (int i = 0; i < count; i++)
        {
            var e = new PckEntry { RawName = names[i], Offset = baseOffset + offsets[i], Size = sizes[i], Depth = depth, Parent = parent };
            into.Add(e);
            All.Add(e);
            if (e.Size >= 8 && BitConverter.ToUInt64(Data.Read(e.Offset, 8)) == Magic1SERpak)
                ReadDirectory(e.Offset, depth + 1, e, e.Children);
        }
    }

    public byte[] ReadEntry(PckEntry e) => Data.Read(e.Offset, e.Size);

    /// <summary>
    /// Finds entries by name. Matches the raw name, the path without category, or the file name
    /// (case-insensitive); '*' and '?' wildcards are allowed. Size-0 entries are references to data
    /// stored in another pak (usually shared.pck) and are skipped unless includeEmpty is set.
    /// </summary>
    public IEnumerable<PckEntry> Find(string pattern, bool includeEmpty = false)
    {
        var rx = WildcardToRegex(pattern);
        return All.Where(e => (includeEmpty || e.Size > 0) &&
            (rx.IsMatch(e.RawName) || rx.IsMatch(e.Path) || rx.IsMatch(e.FileName)));
    }

    /// <summary>Returns the payload entry for a name: for a nested container, its single same-named child.</summary>
    public PckEntry? FindOne(string pattern)
    {
        var hits = Find(pattern).ToList();
        // Prefer leaf entries (a nested 1SERpak wrapping one file has a child with the same file name).
        var leaf = hits.FirstOrDefault(h => !h.IsContainer);
        if (leaf != null) return leaf;
        var c = hits.FirstOrDefault();
        return c?.Children.FirstOrDefault(ch => ch.FileName.Equals(c.FileName, StringComparison.OrdinalIgnoreCase)) ?? c;
    }

    static System.Text.RegularExpressions.Regex WildcardToRegex(string p) =>
        new("^" + System.Text.RegularExpressions.Regex.Escape(p).Replace("\\*", ".*").Replace("\\?", ".") + "$",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    public void Dispose() => Data.Dispose();
}
