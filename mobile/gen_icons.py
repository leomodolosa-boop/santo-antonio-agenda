from PIL import Image
import os

SRC = os.path.join("..", "static", "icons", "icon-512.png")
RES = os.path.join("android", "app", "src", "main", "res")

SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

src = Image.open(SRC).convert("RGBA")

for folder, size in SIZES.items():
    resized = src.resize((size, size), Image.LANCZOS)
    out_dir = os.path.join(RES, folder)
    resized.save(os.path.join(out_dir, "ic_launcher.png"))
    resized.save(os.path.join(out_dir, "ic_launcher_round.png"))
    # foreground adaptive icon uses a larger canvas (108dp vs 72dp legacy) with padding
    fg_size = int(size * 108 / 72)
    canvas = Image.new("RGBA", (fg_size, fg_size), (0, 0, 0, 0))
    pad = fg_size // 6
    inner = fg_size - 2 * pad
    fg = src.resize((inner, inner), Image.LANCZOS)
    canvas.paste(fg, (pad, pad), fg)
    canvas.save(os.path.join(out_dir, "ic_launcher_foreground.png"))

print("Icons generated.")
