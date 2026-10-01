"""
Mini version of image_to_svn - for multiplayer (1000 prop limit).

Grid: 10 x 10 = 100 monitors
Frames: up to 8
Resolution: 60 x 20 pixels (6x2 px per monitor)
Props: ~909 (fits in multiplayer 1000 limit)
"""

import json, sys, os, time, struct
from PIL import Image
from collections import Counter

# ── Configurable ──────────────────────────────────────────────────────────────
MAX_FRAMES     = 8
TIMER_INTERVAL = 0.5

# ── Screen layout ─────────────────────────────────────────────────────────────
PIX_W = 6
PIX_H = 2

MON_COLS = 10
MON_ROWS = 10

IMG_W = MON_COLS * PIX_W   # 60
IMG_H = MON_ROWS * PIX_H   # 20

# ── World space ───────────────────────────────────────────────────────────────
MIN_Y    = 0.53147
STEP_X   = 1.73
STEP_Y   = 1.06
START_X  = -(MON_COLS * STEP_X + 5.0)
Z_SCREEN = 15.0

ROT_FACE = {"x": 0.0, "y": 1.0, "z": 0.0, "w": 5.043734e-09}
ROT_CTRL = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}

CTRL_X       = -80.0
CTRL_Y       = 0.53
CTRL_Z_START = 1.0
CTRL_Z_STEP  = 1.0

def ctrl_pos(index):
    return CTRL_X, CTRL_Y, CTRL_Z_START + index * CTRL_Z_STEP


# ── UniqueID ──────────────────────────────────────────────────────────────────

def _f32(v):
    return struct.unpack('f', struct.pack('f', v))[0]

def uid(x, y, z):
    fx, fy, fz = _f32(x), _f32(y), _f32(z)
    return _f32(_f32(_f32(fx * fx) + _f32(fy * fy)) + _f32(fz * fz))


# ── Color helpers ─────────────────────────────────────────────────────────────

def quantize(v):
    return round(v / 255 * 15) * 17

def to_hex(r, g, b):
    return f"#{quantize(r)//17:X}{quantize(g)//17:X}{quantize(b)//17:X}"


# ── Monitor text ──────────────────────────────────────────────────────────────

def monitor_text(pixel_rows):
    lines = []
    for row in pixel_rows:
        inner = "".join(f"<color={c}>\u2588</color>" for c in row)
        lines.append(f"<b>{inner}</b>")
    return f"<size=136%>{chr(10).join(lines)}</size>"


# ── Frame extraction ──────────────────────────────────────────────────────────

def extract_frames(path, max_frames):
    img = Image.open(path)
    raw_frames = []
    try:
        while True:
            raw_frames.append(img.copy().convert("RGB"))
            img.seek(img.tell() + 1)
    except EOFError:
        pass

    if len(raw_frames) > max_frames:
        step = len(raw_frames) / max_frames
        raw_frames = [raw_frames[int(i * step)] for i in range(max_frames)]

    return [f.resize((IMG_W, IMG_H), Image.LANCZOS) for f in raw_frames]


# ── Monitor world positions ───────────────────────────────────────────────────

def screen_start_y():
    return round(MIN_Y + (MON_ROWS - 1) * STEP_Y, 5)

def mon_pos(col, row, start_y):
    wx = round(START_X + col * STEP_X, 6)
    wy = round(start_y - row * STEP_Y, 5)
    return wx, wy, Z_SCREEN


# ── Per-monitor pixel text ────────────────────────────────────────────────────

def frame_monitor_texts(img):
    pixels = img.load()
    texts, colors = [], []
    for row in range(MON_ROWS):
        for col in range(MON_COLS):
            pixel_rows = []
            all_px = []
            for py in range(PIX_H):
                row_colors = []
                for px in range(PIX_W):
                    r, g, b = pixels[col * PIX_W + px, row * PIX_H + py]
                    c = to_hex(r, g, b)
                    row_colors.append(c)
                    all_px.append(c)
                pixel_rows.append(row_colors)
            dominant = Counter(all_px).most_common(1)[0][0]
            texts.append(monitor_text(pixel_rows))
            colors.append(dominant)
    return texts, colors


# ── Build save ────────────────────────────────────────────────────────────────

def build_save(frames):
    n = len(frames)
    n_monitors = MON_COLS * MON_ROWS
    start_y = screen_start_y()
    props = []

    IDX_BTN = 0
    IDX_TMR = lambda fi: 1 + fi
    IDX_MC  = lambda fi, mi: 1 + n + fi * n_monitors + mi

    frame0_texts, frame0_colors = frame_monitor_texts(frames[0])

    monitor_uids = []
    for row in range(MON_ROWS):
        for col in range(MON_COLS):
            mi = row * MON_COLS + col
            wx, wy, wz = mon_pos(col, row, start_y)
            mon_uid = uid(wx, wy, wz)
            monitor_uids.append(mon_uid)
            props.append({
                "name": "Monitor",
                "uniqueId": mon_uid,
                "position": {"x": wx, "y": wy, "z": wz},
                "rotation": ROT_FACE,
                "isKinematic": True,
                "instantiationData": None,
                "runtimeData": {
                    "connectedIds": [],
                    "Text": frame0_texts[mi],
                    "Color": frame0_colors[mi]
                }
            })

    mc_uid_grid = [
        [uid(*ctrl_pos(IDX_MC(fi, mi))) for mi in range(n_monitors)]
        for fi in range(n)
    ]
    timer_uid_list = [uid(*ctrl_pos(IDX_TMR(fi))) for fi in range(n)]
    btn_uid = uid(*ctrl_pos(IDX_BTN))

    bx, by, bz = ctrl_pos(IDX_BTN)
    props.append({
        "name": "Button",
        "uniqueId": btn_uid,
        "position": {"x": bx, "y": by, "z": bz},
        "rotation": ROT_CTRL,
        "isKinematic": True,
        "instantiationData": {"Toggle": False},
        "runtimeData": {"connectedIds": [timer_uid_list[0]], "Signal": False}
    })

    for fi in range(n):
        x, y, z = ctrl_pos(IDX_TMR(fi))
        connected = mc_uid_grid[fi] + [timer_uid_list[(fi + 1) % n]]
        props.append({
            "name": "Timer",
            "uniqueId": timer_uid_list[fi],
            "position": {"x": x, "y": y, "z": z},
            "rotation": ROT_CTRL,
            "isKinematic": True,
            "instantiationData": {"Time": TIMER_INTERVAL},
            "runtimeData": {"connectedIds": connected}
        })

    for fi in range(n):
        frame_texts, _ = frame_monitor_texts(frames[fi])
        for mi in range(n_monitors):
            x, y, z = ctrl_pos(IDX_MC(fi, mi))
            props.append({
                "name": "MonitorController",
                "uniqueId": mc_uid_grid[fi][mi],
                "position": {"x": x, "y": y, "z": z},
                "rotation": ROT_CTRL,
                "isKinematic": True,
                "instantiationData": {
                    "Text": frame_texts[mi],
                    "Background color": "Black"
                },
                "runtimeData": {"connectedIds": [monitor_uids[mi]]}
            })

    return {"map": "FlatGrass", "props": props}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python image_to_svn_mini.py animation.gif [output.svn]")
        sys.exit(1)

    output_path = None
    if args[-1].endswith(".svn"):
        output_path = args[-1]
        args = args[:-1]

    input_path = args[0]
    if not os.path.isfile(input_path):
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    print(f"Loading: {input_path}")
    frames = extract_frames(input_path, MAX_FRAMES)
    n = len(frames)
    print(f"Frames  : {n}  (MAX_FRAMES={MAX_FRAMES})")
    print(f"Image   : {IMG_W}x{IMG_H} px  ({MON_COLS}x{MON_ROWS} monitors)")

    print("Building save... ", end="", flush=True)
    data = build_save(frames)
    print("done")

    total_props = len(data["props"])
    print(f"Total props: {total_props} (multiplayer limit: 1000)")

    if output_path is None:
        ts = int(time.time() * 1000)
        output_path = os.path.join(os.path.dirname(os.path.abspath(input_path)),
                                   f"mini_{ts}.svn")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Output  : {output_path}")


if __name__ == "__main__":
    main()