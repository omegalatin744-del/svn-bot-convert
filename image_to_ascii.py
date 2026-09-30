"""
Converts an image (GIF/PNG/JPG) into a single string of 115 ASCII characters.
Resolution: 23 chars wide x 5 chars tall = 115 chars.
Bright pixels -> dense chars, dark pixels -> light chars.
No spaces, no line breaks - all in one line.
"""

import sys
import os
from PIL import Image, ImageOps

OUT_W = 23
OUT_H = 5

# Variant C (30 chars). First char = brightest, last = darkest.
CHARS = "@%#WM8B&$*oahkbdpqwmZO0QLCJUYX"


def image_to_ascii_string(img):
    img = img.convert("L")  # grayscale
    img = img.resize((OUT_W, OUT_H), Image.LANCZOS)
    img = ImageOps.autocontrast(img)

    pixels = img.load()
    result = []

    for row in range(OUT_H):
        for col in range(OUT_W):
            value = pixels[col, row]  # 0..255
            # Invert: bright pixel (255) -> index 0 (dense '@')
            idx = round((255 - value) / 255 * (len(CHARS) - 1))
            idx = max(0, min(len(CHARS) - 1, idx))
            result.append(CHARS[idx])

    return "".join(result)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python image_to_ascii.py image.png [output.txt]")
        sys.exit(1)

    output_path = None
    if args[-1].endswith(".txt"):
        output_path = args[-1]
        args = args[:-1]

    input_path = args[0]
    if not os.path.isfile(input_path):
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    img = Image.open(input_path)
    result = image_to_ascii_string(img)

    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".ascii.txt"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"ASCII ({len(result)} chars): {result}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()