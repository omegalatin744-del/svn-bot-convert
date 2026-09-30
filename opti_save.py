"""
Opti-save: compress / decompress .svn files with full reversibility.

Compression:
  - Short keys (uniqueId -> i, position -> p, etc.)
  - name values replaced with numeric IDs stored in a lookup table ("nm")
  - Compact JSON (no whitespace)
  Result: .svnz file

Decompression:
  - Reverse everything, restore original .svn (with indent=2)

Usage:
  python opti_save.py compress input.svn  output.svnz
  python opti_save.py decompress input.svnz output.svn
"""

import json
import sys
import os


# ── Key mapping ───────────────────────────────────────────────────────────────

KEY_MAP = {
    "name": "n",
    "uniqueId": "i",
    "position": "p",
    "rotation": "r",
    "isKinematic": "k",
    "instantiationData": "d",
    "runtimeData": "u",
    "connectedIds": "c",
    "Text": "t",
    "Color": "o",
    "Background color": "b",
    "Toggle": "g",
    "Signal": "s",
    "Time": "m",
}
KEY_MAP_REV = {v: k for k, v in KEY_MAP.items()}


def compress_keys(obj):
    """Recursively rename keys."""
    if isinstance(obj, dict):
        return {KEY_MAP.get(k, k): compress_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [compress_keys(x) for x in obj]
    return obj


def decompress_keys(obj):
    """Recursively restore original key names."""
    if isinstance(obj, dict):
        return {KEY_MAP_REV.get(k, k): decompress_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decompress_keys(x) for x in obj]
    return obj


# ── Name table ────────────────────────────────────────────────────────────────

def build_name_table(data):
    """Collect unique 'name' values into a dict {name: index}."""
    names = {}
    for p in data.get("props", []):
        n = p.get("name")
        if isinstance(n, str) and n not in names:
            names[n] = len(names) + 1
    return names


def apply_name_table(data, names):
    """Replace name strings with numbers."""
    for p in data.get("props", []):
        n = p.get("name")
        if isinstance(n, str) and n in names:
            p["name"] = names[n]
    return data


def restore_name_table(data, names_rev):
    """Replace numeric names back with strings."""
    for p in data.get("props", []):
        n = p.get("name")
        if isinstance(n, int) and n in names_rev:
            p["name"] = names_rev[n]
    return data


# ── Compress / Decompress ─────────────────────────────────────────────────────

def compress(data):
    names = build_name_table(data)
    data = apply_name_table(data, names)
    data = compress_keys(data)
    # Store the name table inside the file for restoration
    data["nm"] = {str(v): k for k, v in names.items()}
    return data


def decompress(data):
    names_rev = {}
    nm = data.pop("nm", {})
    for k, v in nm.items():
        names_rev[int(k)] = v

    data = decompress_keys(data)
    data = restore_name_table(data, names_rev)
    return data


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if len(args) < 3:
        print("Usage:")
        print("  python opti_save.py compress   input.svn  output.svnz")
        print("  python opti_save.py decompress input.svnz output.svn")
        sys.exit(1)

    action = args[0]
    input_path = args[1]
    output_path = args[2]

    if not os.path.isfile(input_path):
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if action == "compress":
        data = compress(data)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    elif action == "decompress":
        data = decompress(data)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    in_kb = os.path.getsize(input_path) / 1024
    out_kb = os.path.getsize(output_path) / 1024
    ratio = (out_kb / in_kb * 100) if in_kb else 0
    print(f"Done: {in_kb:.1f} KB -> {out_kb:.1f} KB ({ratio:.0f}%)")


if __name__ == "__main__":
    main()