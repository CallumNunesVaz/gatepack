"""Render the gatepack logo set and assemble a multi-resolution .ico."""
import struct, pathlib, cairosvg

MEDIA = pathlib.Path("/home/callum/Documents/gatepack/media")
PNG = MEDIA / "png"
PNG.mkdir(parents=True, exist_ok=True)

MARK = MEDIA / "gatepack-mark.svg"
SMALL = MEDIA / "gatepack-mark-small.svg"
LOGO = MEDIA / "gatepack-logo.svg"

# Below 48px the detailed mark turns to mush, so the simplified variant is the
# source there. Using one source for every size is what makes a favicon look
# like a smudge.
def source_for(size: int) -> pathlib.Path:
    return SMALL if size <= 48 else MARK

ICON_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024]
for s in ICON_SIZES:
    cairosvg.svg2png(url=str(source_for(s)), write_to=str(PNG / f"gatepack-{s}.png"),
                     output_width=s, output_height=s)

# Horizontal lockup, 1x and 2x, on transparent and on white.
cairosvg.svg2png(url=str(LOGO), write_to=str(PNG / "gatepack-logo.png"), output_width=1120)
cairosvg.svg2png(url=str(LOGO), write_to=str(PNG / "gatepack-logo@2x.png"), output_width=2240)

# ---- .ico -------------------------------------------------------------
# Written by hand rather than via Pillow's `sizes=`, which resamples from a
# single source; this embeds the per-size PNGs chosen above.
ico_sizes = [16, 32, 48, 64, 128, 256]
payloads = [(s, (PNG / f"gatepack-{s}.png").read_bytes()) for s in ico_sizes]

header = struct.pack("<HHH", 0, 1, len(payloads))   # reserved, type=icon, count
offset = 6 + 16 * len(payloads)
entries, blobs = b"", b""
for size, data in payloads:
    # 256 is encoded as 0 in the directory, per the ICO format.
    dim = 0 if size >= 256 else size
    entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
    blobs += data
    offset += len(data)

(MEDIA / "gatepack.ico").write_bytes(header + entries + blobs)
print("ico entries:", ico_sizes)
print("png sizes:", ICON_SIZES)
