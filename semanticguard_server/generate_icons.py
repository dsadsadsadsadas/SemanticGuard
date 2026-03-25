#!/usr/bin/env python3
"""
Generate SemanticGuard Gatekeeper icon PNGs.
No Pillow required. Tries backends in order:
  1. cv2 (OpenCV)     — likely in ML envs
  2. imageio          - pip install imageio
  3. Pure stdlib+numpy — guaranteed (torch dependency)

Usage:
    python generate_icons.py path/to/source.png
"""

import sys
import struct
import zlib
from pathlib import Path

SIZES = [16, 48, 128, 512]


def generate_icons(source_path: Path, output_dir: Path):
    # ── 1. OpenCV ──────────────────────────────────────────
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(source_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError("cv2 returned None — unreadable format")
        h, w = img.shape[:2]
        print(f"Source: {source_path.name} ({w}×{h})  [cv2]")
        output_dir.mkdir(parents=True, exist_ok=True)
        for s in SIZES:
            out = output_dir / f"icon{s}.png"
            cv2.imwrite(str(out), cv2.resize(img, (s, s), interpolation=cv2.INTER_LANCZOS4))
            print(f"  ✅ icon{s}.png")
        print(f"\n✨ {output_dir.resolve()}")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[cv2 failed: {e}] — trying imageio")

    # ── 2. imageio ─────────────────────────────────────────
    try:
        import imageio.v3 as iio
        import numpy as np
        img = iio.imread(str(source_path))          # handles PNG, WebP, JPEG
        if img.ndim == 2:                            # grayscale → RGBA
            img = np.stack([img]*3 + [np.full_like(img, 255)], axis=-1)
        elif img.shape[2] == 3:                      # RGB → RGBA
            img = np.concatenate([img, np.full((*img.shape[:2], 1), 255, np.uint8)], axis=-1)
        h, w = img.shape[:2]
        print(f"Source: {source_path.name} ({w}×{h})  [imageio]")
        output_dir.mkdir(parents=True, exist_ok=True)
        for s in SIZES:
            out = output_dir / f"icon{s}.png"
            iio.imwrite(str(out), _resize(img, s, np))
            print(f"  ✅ icon{s}.png")
        print(f"\n✨ {output_dir.resolve()}")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[imageio failed: {e}] — trying pure Python")

    # ── 3. Pure stdlib + numpy ─────────────────────────────
    try:
        import numpy as np
        img = _read_png_pure(source_path, np)
        h, w = img.shape[:2]
        print(f"Source: {source_path.name} ({w}×{h})  [pure Python+numpy]")
        output_dir.mkdir(parents=True, exist_ok=True)
        for s in SIZES:
            out = output_dir / f"icon{s}.png"
            _write_png_pure(_resize(img, s, np), out)
            print(f"  ✅ icon{s}.png")
        print(f"\n✨ {output_dir.resolve()}")
        return
    except ImportError:
        pass

    print("❌ No image backend available.")
    print("   Run:  pip install imageio   or   conda install opencv")
    sys.exit(1)


# ─── Bilinear resize (numpy) ───────────────────────────────

def _resize(img, size, np):
    oh, ow = img.shape[:2]
    yi = np.linspace(0, oh-1, size); xi = np.linspace(0, ow-1, size)
    y0 = np.floor(yi).astype(int).clip(0, oh-2)
    x0 = np.floor(xi).astype(int).clip(0, ow-2)
    fy = (yi-y0)[:,None,None]; fx = (xi-x0)[None,:,None]
    return (img[y0][:,x0]*(1-fy)*(1-fx) + img[y0][:,x0+1]*(1-fy)*fx
          + img[y0+1][:,x0]     *fy*(1-fx) + img[y0+1][:,x0+1]*fy*fx).astype(np.uint8)


# ─── Pure Python PNG reader ────────────────────────────────

def _read_png_pure(path, np):
    data = path.read_bytes()
    sig = data[:8]
    # Accept PNG and also WebP (RIFF....WEBP) — raise clear error for WebP
    if sig == b'RIFF' + data[4:8][:0] or data[8:12] == b'WEBP':
        raise ValueError("Source is WebP — use imageio or cv2 backend")
    if sig != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f"Unknown format (magic: {sig[:4].hex()})")

    pos, idat, width, height, color_type = 8, [], 0, 0, 0
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        tag = data[pos+4:pos+8]; body = data[pos+8:pos+8+length]; pos += 12+length
        if tag == b'IHDR': width, height = struct.unpack('>II', body[:8]); color_type = body[9]
        elif tag == b'IDAT': idat.append(body)
        elif tag == b'IEND': break

    raw = zlib.decompress(b''.join(idat))
    ch = {2:3, 6:4, 0:1, 4:2}.get(color_type, 3)
    stride = width*ch+1
    img = np.zeros((height, width, 4), dtype=np.uint8)
    prev = np.zeros(width*ch, dtype=np.int32)

    for y in range(height):
        f = raw[y*stride]; row = np.frombuffer(raw[y*stride+1:y*stride+1+width*ch], np.uint8).astype(np.int32)
        if f==1:
            for i in range(ch, len(row)): row[i]=(row[i]+row[i-ch])&0xFF
        elif f==2: row=(row+prev)&0xFF
        elif f==3:
            for i in range(len(row)): a=row[i-ch] if i>=ch else 0; row[i]=(row[i]+(a+prev[i])//2)&0xFF
        elif f==4:
            for i in range(len(row)):
                a=row[i-ch] if i>=ch else 0; b=prev[i]; c=prev[i-ch] if i>=ch else 0
                p=a+b-c; pr=a if abs(p-a)<=abs(p-b) and abs(p-a)<=abs(p-c) else (b if abs(p-b)<=abs(p-c) else c)
                row[i]=(row[i]+pr)&0xFF
        prev=row.copy(); pix=row.reshape(width,ch).astype(np.uint8)
        if ch==4: img[y]=pix
        elif ch==3: img[y,:,:3]=pix; img[y,:,3]=255
        else: img[y,:,:3]=pix[:,[0,0,0]]; img[y,:,3]=255
    return img


def _write_png_pure(img, path):
    h, w = img.shape[:2]
    def ck(t,b): crc=zlib.crc32(t+b)&0xFFFFFFFF; return struct.pack('>I',len(b))+t+b+struct.pack('>I',crc)
    rows = b''.join(b'\x00'+img[y].tobytes() for y in range(h))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
        + ck(b'IHDR', struct.pack('>IIBBBBB',w,h,8,6,0,0,0))
        + ck(b'IDAT', zlib.compress(rows,9))
        + ck(b'IEND', b''))


# ─── Entry point ───────────────────────────────────────────

def main():
    icons_dir = Path(__file__).parent.parent / "extension" / "icons"
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else next(
        iter(sorted(Path(__file__).parent.glob("semanticguard_icon*.png"))), None)
    if not source or not source.exists():
        print("Usage: python generate_icons.py <source_image>"); sys.exit(1)
    generate_icons(source, icons_dir)

if __name__ == "__main__":
    main()
