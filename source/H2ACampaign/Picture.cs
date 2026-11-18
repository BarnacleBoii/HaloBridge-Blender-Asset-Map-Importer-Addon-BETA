using System.Buffers.Binary;
using System.IO.Compression;

namespace HaloBridge.H2ACampaign;

/// <summary>Picture formats seen in .pct files (values from LibSaber's PictureFormat, verified on data).</summary>
public enum PictureFormat
{
    A8R8G8B8 = 0x00,
    A8L8 = 0x0A,
    OXT1 = 0x0C,      // BC1, opaque
    AXT1 = 0x0D,      // BC1 with 1-bit alpha
    DXT3 = 0x0F,      // BC2
    DXT5 = 0x11,      // BC3
    X8R8G8B8 = 0x16,
    DXN = 0x24,       // BC5 (two-channel normal map)
    DXT5A = 0x25,     // BC4 (single channel)
    A16B16G16R16F = 0x26,
    R9G9B9E5 = 0x2D,
}

/// <summary>
/// A Saber3D .pct texture. The file is a list of sentinel blocks: int16 id, int32 absolute end
/// offset, payload. 0xF0 = "TCIP" magic, 0x102 = width/height/depth/faces, 0xF2 = format,
/// 0xF9 = mip count, 0xFF = pixel data, 0x01 = end.
/// </summary>
public sealed class Picture
{
    public int Width, Height, Depth = 1, Faces = 1, MipCount = 1, FormatValue;
    public byte[] Data = [];
    public int DataOffset;
    public List<string> UnknownBlocks { get; } = [];

    public PictureFormat Format => (PictureFormat)FormatValue;
    public bool IsCube => Faces == 6;
    public int Slices => Math.Max(1, Faces) * Math.Max(1, Depth);

    public static Picture Parse(byte[] b)
    {
        var p = new Picture();
        int pos = 0;
        bool sawMagic = false, sawData = false;
        while (pos + 6 <= b.Length)
        {
            short id = BinaryPrimitives.ReadInt16LittleEndian(b.AsSpan(pos));
            int end = BinaryPrimitives.ReadInt32LittleEndian(b.AsSpan(pos + 2));
            int body = pos + 6;
            if (id == 0x0001) break;
            if (end < body || end > b.Length) throw new InvalidDataException($"Bad sentinel 0x{id:X} end 0x{end:X} at 0x{pos:X}.");
            var s = b.AsSpan(body);
            switch (id)
            {
                case 0x00F0:
                    if (BinaryPrimitives.ReadUInt32LittleEndian(s) != 0x50494354) throw new InvalidDataException("Missing TCIP magic.");
                    sawMagic = true; break;
                case 0x0102:
                    p.Width = BinaryPrimitives.ReadInt32LittleEndian(s);
                    p.Height = BinaryPrimitives.ReadInt32LittleEndian(s[4..]);
                    p.Depth = BinaryPrimitives.ReadInt32LittleEndian(s[8..]);
                    p.Faces = BinaryPrimitives.ReadInt32LittleEndian(s[12..]);
                    break;
                case 0x00F2: p.FormatValue = BinaryPrimitives.ReadInt32LittleEndian(s); break;
                case 0x00F9: p.MipCount = BinaryPrimitives.ReadInt32LittleEndian(s); break;
                case 0x00FF: p.DataOffset = body; p.Data = b[body..end]; sawData = true; break;
                default: p.UnknownBlocks.Add($"0x{id:X}[{end - body}]"); break;
            }
            pos = end;
        }
        if (!sawMagic || !sawData) throw new InvalidDataException("Not a .pct picture (missing TCIP or data block).");
        if (!Enum.IsDefined(p.Format)) throw new NotSupportedException($"Unknown picture format 0x{p.FormatValue:X}.");
        return p;
    }

    public static int BlockBytes(PictureFormat f) => f switch
    {
        PictureFormat.OXT1 or PictureFormat.AXT1 or PictureFormat.DXT5A => 8,
        PictureFormat.DXT3 or PictureFormat.DXT5 or PictureFormat.DXN => 16,
        _ => 0,
    };

    public static int PixelBytes(PictureFormat f) => f switch
    {
        PictureFormat.A8R8G8B8 or PictureFormat.X8R8G8B8 or PictureFormat.R9G9B9E5 => 4,
        PictureFormat.A8L8 => 2,
        PictureFormat.A16B16G16R16F => 8,
        _ => 0,
    };

    public int MipBytes(int mip)
    {
        int w = Math.Max(1, Width >> mip), h = Math.Max(1, Height >> mip);
        int bb = BlockBytes(Format);
        return bb > 0 ? Math.Max(1, (w + 3) / 4) * Math.Max(1, (h + 3) / 4) * bb : w * h * PixelBytes(Format);
    }

    public int ChainBytes => Enumerable.Range(0, Math.Max(1, MipCount)).Sum(MipBytes);
    public long ExpectedBytes => (long)ChainBytes * Slices;

    /// <summary>
    /// Offset of (slice, mip) in Data. Layout (verified visually on cube maps): face-major like DDS,
    /// i.e. face 0 with its whole mip chain (largest first), then face 1, and so on.
    /// </summary>
    public int OffsetOf(int slice, int mip)
    {
        int off = ChainBytes * slice;
        for (int m = 0; m < mip; m++) off += MipBytes(m);
        return off;
    }

    public override string ToString() =>
        $"{Width}x{Height} depth={Depth} faces={Faces} mips={MipCount} format={Format}(0x{FormatValue:X}) data={Data.Length} expected={ExpectedBytes}" +
        (UnknownBlocks.Count > 0 ? " unknown=" + string.Join(",", UnknownBlocks) : "");

    public byte[] DecodeRgba(int slice, int mip)
    {
        int w = Math.Max(1, Width >> mip), h = Math.Max(1, Height >> mip);
        int off = OffsetOf(slice, mip);
        int len = MipBytes(mip);
        if (off + len > Data.Length) throw new InvalidDataException($"Data too short for slice {slice} mip {mip} ({off + len} > {Data.Length}).");
        return TextureDecoder.Decode(Format, Data.AsSpan(off, len), w, h);
    }

    public IEnumerable<string> WritePngs(string basePath, bool allMips)
    {
        int mips = allMips ? Math.Max(1, MipCount) : 1;
        for (int s = 0; s < Slices; s++)
            for (int m = 0; m < mips; m++)
            {
                var suffix = (Slices > 1 ? (IsCube && Depth <= 1 ? $"_face{s}" : $"_slice{s}") : "") + (allMips ? $"_mip{m}" : "");
                var path = basePath + suffix + ".png";
                int w = Math.Max(1, Width >> m), h = Math.Max(1, Height >> m);
                Png.Write(path, DecodeRgba(s, m), w, h);
                yield return path;
            }
    }

    public bool IsBlockCompressed => BlockBytes(Format) > 0;

    /// <summary>
    /// A DX10 DDS holding only mip level <paramref name="mip"/> of slice 0, the original block data unchanged.
    /// Blender (4.4 and 5.2 checked) loads BC1/BC3/BC4/BC5 DDS directly, so a texture needs no PNG copy;
    /// Blender builds its own mipmaps, so the rest of the chain is left out.
    /// </summary>
    public byte[] ToDdsMip(int mip)
    {
        var single = new Picture
        {
            Width = Math.Max(1, Width >> mip), Height = Math.Max(1, Height >> mip), Depth = 1, Faces = 1, MipCount = 1,
            FormatValue = FormatValue, Data = Data.AsSpan(OffsetOf(0, mip), MipBytes(mip)).ToArray(),
        };
        return single.ToDds();
    }

    /// <summary>Writes a DX10 DDS (face-major) so the original block data is kept losslessly.</summary>
    public byte[] ToDds()
    {
        int dxgi = Format switch
        {
            PictureFormat.OXT1 or PictureFormat.AXT1 => 71,
            PictureFormat.DXT3 => 74,
            PictureFormat.DXT5 => 77,
            PictureFormat.DXT5A => 80,
            PictureFormat.DXN => 83,
            PictureFormat.A8R8G8B8 => 87,
            PictureFormat.X8R8G8B8 => 88,
            PictureFormat.A16B16G16R16F => 10,
            PictureFormat.R9G9B9E5 => 67,
            PictureFormat.A8L8 => 49,
            _ => throw new NotSupportedException(),
        };
        using var ms = new MemoryStream();
        using var w = new BinaryWriter(ms);
        int mips = Math.Max(1, MipCount);
        w.Write(0x20534444u); // "DDS "
        w.Write(124);
        w.Write(0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | (BlockBytes(Format) > 0 ? 0x80000 : 0x8));
        w.Write(Height); w.Write(Width);
        w.Write(BlockBytes(Format) > 0 ? MipBytes(0) : Width * PixelBytes(Format));
        w.Write(Depth > 1 ? Depth : 0); w.Write(mips);
        for (int i = 0; i < 11; i++) w.Write(0);
        w.Write(32); w.Write(0x4); w.Write(0x30315844u); // pixel format: FOURCC "DX10"
        for (int i = 0; i < 5; i++) w.Write(0);
        w.Write(0x1000 | (mips > 1 ? 0x400008 : 0) | (IsCube ? 0x8 : 0));
        w.Write(IsCube ? 0xFE00 : 0); w.Write(0); w.Write(0); w.Write(0);
        // DX10 header
        w.Write(dxgi); w.Write(Depth > 1 ? 4 : 3); w.Write(IsCube ? 0x4 : 0);
        w.Write(IsCube ? Faces / 6 : (Depth > 1 ? 1 : Faces)); w.Write(0);
        for (int s = 0; s < Slices; s++)
            for (int m = 0; m < mips; m++)
                w.Write(Data, OffsetOf(s, m), MipBytes(m));
        return ms.ToArray();
    }
}

static class TextureDecoder
{
    public static byte[] Decode(PictureFormat f, ReadOnlySpan<byte> src, int w, int h)
    {
        var dst = new byte[w * h * 4];
        switch (f)
        {
            case PictureFormat.OXT1:
            case PictureFormat.AXT1:
            case PictureFormat.DXT3:
            case PictureFormat.DXT5:
            case PictureFormat.DXT5A:
            case PictureFormat.DXN:
                DecodeBlocks(f, src, w, h, dst); break;
            case PictureFormat.A8R8G8B8:
            case PictureFormat.X8R8G8B8:
                for (int i = 0; i < w * h; i++)
                {
                    dst[i * 4] = src[i * 4 + 2]; dst[i * 4 + 1] = src[i * 4 + 1]; dst[i * 4 + 2] = src[i * 4];
                    dst[i * 4 + 3] = f == PictureFormat.X8R8G8B8 ? (byte)255 : src[i * 4 + 3];
                }
                break;
            case PictureFormat.A8L8:
                for (int i = 0; i < w * h; i++) { dst[i * 4] = dst[i * 4 + 1] = dst[i * 4 + 2] = src[i * 2]; dst[i * 4 + 3] = src[i * 2 + 1]; }
                break;
            case PictureFormat.A16B16G16R16F:
                for (int i = 0; i < w * h; i++)
                    for (int c = 0; c < 4; c++)
                    {
                        float v = (float)BinaryPrimitives.ReadHalfLittleEndian(src.Slice(i * 8 + c * 2));
                        dst[i * 4 + c] = c == 3 ? ToByte(v) : ToSrgbByte(v);
                    }
                break;
            case PictureFormat.R9G9B9E5:
                for (int i = 0; i < w * h; i++)
                {
                    uint v = BinaryPrimitives.ReadUInt32LittleEndian(src.Slice(i * 4));
                    float scale = MathF.Pow(2, (int)(v >> 27) - 15 - 9);
                    dst[i * 4] = ToSrgbByte((v & 0x1FF) * scale);
                    dst[i * 4 + 1] = ToSrgbByte(((v >> 9) & 0x1FF) * scale);
                    dst[i * 4 + 2] = ToSrgbByte(((v >> 18) & 0x1FF) * scale);
                    dst[i * 4 + 3] = 255;
                }
                break;
            default: throw new NotSupportedException(f.ToString());
        }
        return dst;
    }

    static byte ToByte(float v) => (byte)Math.Clamp((int)MathF.Round(v * 255f), 0, 255);
    // HDR preview: clamp linear radiance to [0,1] and encode as sRGB.
    static byte ToSrgbByte(float v)
    {
        v = Math.Clamp(float.IsNaN(v) ? 0 : v, 0, 1);
        return ToByte(v <= 0.0031308f ? v * 12.92f : 1.055f * MathF.Pow(v, 1 / 2.4f) - 0.055f);
    }

    static void DecodeBlocks(PictureFormat f, ReadOnlySpan<byte> src, int w, int h, byte[] dst)
    {
        int bw = Math.Max(1, (w + 3) / 4), bh = Math.Max(1, (h + 3) / 4);
        int bb = Picture.BlockBytes(f);
        Span<byte> block = stackalloc byte[64];
        for (int by = 0; by < bh; by++)
            for (int bx = 0; bx < bw; bx++)
            {
                var s = src.Slice((by * bw + bx) * bb, bb);
                block.Clear();
                switch (f)
                {
                    case PictureFormat.OXT1: Color(s, block, true, f == PictureFormat.AXT1); break;
                    case PictureFormat.AXT1: Color(s, block, true, true); break;
                    case PictureFormat.DXT3:
                        Color(s[8..], block, false, false);
                        for (int i = 0; i < 16; i++) block[i * 4 + 3] = (byte)(((s[i / 2] >> (4 * (i & 1))) & 0xF) * 17);
                        break;
                    case PictureFormat.DXT5:
                        Color(s[8..], block, false, false);
                        Alpha(s, block, 3);
                        break;
                    case PictureFormat.DXT5A:
                        Alpha(s, block, 0);
                        for (int i = 0; i < 16; i++) { block[i * 4 + 1] = block[i * 4 + 2] = block[i * 4]; block[i * 4 + 3] = 255; }
                        break;
                    case PictureFormat.DXN:
                        Alpha(s, block, 0);
                        Alpha(s[8..], block, 1);
                        for (int i = 0; i < 16; i++)
                        {
                            float x = block[i * 4] / 127.5f - 1, y = block[i * 4 + 1] / 127.5f - 1;
                            float z = MathF.Sqrt(Math.Max(0, 1 - x * x - y * y));
                            block[i * 4 + 2] = ToByte(z * 0.5f + 0.5f);
                            block[i * 4 + 3] = 255;
                        }
                        break;
                }
                for (int py = 0; py < 4; py++)
                {
                    int y = by * 4 + py; if (y >= h) break;
                    for (int px = 0; px < 4; px++)
                    {
                        int x = bx * 4 + px; if (x >= w) break;
                        block.Slice((py * 4 + px) * 4, 4).CopyTo(dst.AsSpan((y * w + x) * 4));
                    }
                }
            }
    }

    static void Color(ReadOnlySpan<byte> s, Span<byte> block, bool allowPunchThrough, bool alpha)
    {
        ushort c0 = BinaryPrimitives.ReadUInt16LittleEndian(s), c1 = BinaryPrimitives.ReadUInt16LittleEndian(s[2..]);
        Span<int> pal = stackalloc int[16];
        for (int i = 0; i < 2; i++)
        {
            int c = i == 0 ? c0 : c1;
            pal[i * 4] = (c >> 11) * 255 / 31; pal[i * 4 + 1] = ((c >> 5) & 63) * 255 / 63; pal[i * 4 + 2] = (c & 31) * 255 / 31; pal[i * 4 + 3] = 255;
        }
        bool four = !allowPunchThrough || c0 > c1;
        for (int c = 0; c < 3; c++)
        {
            if (four) { pal[8 + c] = (2 * pal[c] + pal[4 + c]) / 3; pal[12 + c] = (pal[c] + 2 * pal[4 + c]) / 3; }
            else { pal[8 + c] = (pal[c] + pal[4 + c]) / 2; pal[12 + c] = 0; }
        }
        pal[11] = 255; pal[15] = four || !alpha ? 255 : 0;
        uint idx = BinaryPrimitives.ReadUInt32LittleEndian(s[4..]);
        for (int i = 0; i < 16; i++)
        {
            int k = (int)((idx >> (2 * i)) & 3);
            for (int c = 0; c < 4; c++) block[i * 4 + c] = (byte)pal[k * 4 + c];
        }
    }

    static void Alpha(ReadOnlySpan<byte> s, Span<byte> block, int channel)
    {
        int a0 = s[0], a1 = s[1];
        Span<int> pal = stackalloc int[8];
        pal[0] = a0; pal[1] = a1;
        if (a0 > a1) for (int i = 1; i < 7; i++) pal[i + 1] = ((7 - i) * a0 + i * a1) / 7;
        else { for (int i = 1; i < 5; i++) pal[i + 1] = ((5 - i) * a0 + i * a1) / 5; pal[6] = 0; pal[7] = 255; }
        ulong bits = 0;
        for (int i = 0; i < 6; i++) bits |= (ulong)s[2 + i] << (8 * i);
        for (int i = 0; i < 16; i++) block[i * 4 + channel] = (byte)pal[(int)((bits >> (3 * i)) & 7)];
    }
}

public static class Png
{
    static readonly uint[] Crc = Enumerable.Range(0, 256).Select(n =>
    {
        uint c = (uint)n;
        for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
        return c;
    }).ToArray();

    public static void Write(string path, byte[] rgba, int w, int h, bool small = false)
    {
        File.WriteAllBytes(path, Encode(rgba, w, h, small));
    }

    /// <summary>
    /// PNG bytes. small = true stores RGB when every alpha is 255, picks a per-row filter (minimum
    /// sum of absolute differences, the usual heuristic) and uses the strongest deflate level.
    /// </summary>
    public static byte[] Encode(byte[] rgba, int w, int h, bool small = false)
    {
        bool rgb = small && Enumerable.Range(0, w * h).All(i => rgba[i * 4 + 3] == 255);
        int bpp = rgb ? 3 : 4, stride = w * bpp;
        var pixels = rgba;
        if (rgb)
        {
            pixels = new byte[w * h * 3];
            for (int i = 0; i < w * h; i++) { pixels[i * 3] = rgba[i * 4]; pixels[i * 3 + 1] = rgba[i * 4 + 1]; pixels[i * 3 + 2] = rgba[i * 4 + 2]; }
        }
        using var fs = new MemoryStream();
        fs.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
        var ihdr = new byte[13];
        BinaryPrimitives.WriteInt32BigEndian(ihdr, w);
        BinaryPrimitives.WriteInt32BigEndian(ihdr.AsSpan(4), h);
        ihdr[8] = 8; ihdr[9] = (byte)(rgb ? 2 : 6);
        Chunk(fs, "IHDR", ihdr);
        using var raw = new MemoryStream();
        using (var z = new ZLibStream(raw, small ? CompressionLevel.SmallestSize : CompressionLevel.Fastest, leaveOpen: true))
        {
            var prev = new byte[stride];
            var best = new byte[stride];
            var trial = new byte[stride];
            for (int y = 0; y < h; y++)
            {
                var row = pixels.AsSpan(y * stride, stride);
                if (!small) { z.WriteByte(0); z.Write(row); continue; }
                long bestScore = long.MaxValue; byte bestType = 0;
                for (byte type = 0; type < 5; type++)
                {
                    long score = 0;
                    for (int x = 0; x < stride; x++)
                    {
                        int a = x >= bpp ? row[x - bpp] : 0, b = prev[x], c = x >= bpp ? prev[x - bpp] : 0;
                        int pred = type switch { 0 => 0, 1 => a, 2 => b, 3 => (a + b) >> 1, _ => Paeth(a, b, c) };
                        byte v = (byte)(row[x] - pred);
                        trial[x] = v;
                        score += v < 128 ? v : 256 - v;
                    }
                    if (score < bestScore) { bestScore = score; bestType = type; trial.CopyTo(best, 0); }
                }
                z.WriteByte(bestType); z.Write(best);
                row.CopyTo(prev);
            }
        }
        Chunk(fs, "IDAT", raw.ToArray());
        Chunk(fs, "IEND", []);
        return fs.ToArray();
    }

    static int Paeth(int a, int b, int c)
    {
        int p = a + b - c, pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
        return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
    }

    static void Chunk(Stream s, string type, byte[] data)
    {
        Span<byte> b4 = stackalloc byte[4];
        BinaryPrimitives.WriteInt32BigEndian(b4, data.Length); s.Write(b4);
        var t = System.Text.Encoding.ASCII.GetBytes(type);
        s.Write(t); s.Write(data);
        uint c = 0xFFFFFFFF;
        foreach (var x in t) c = Crc[(c ^ x) & 0xFF] ^ (c >> 8);
        foreach (var x in data) c = Crc[(c ^ x) & 0xFF] ^ (c >> 8);
        BinaryPrimitives.WriteUInt32BigEndian(b4, ~c); s.Write(b4);
    }
}
