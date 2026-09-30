"""
Converts a GIF (or PNG/JPG) into a Unity save file (.svn) — VideoPlayer style.

  GIF input:  python image_to_svn.py animation.gif [output.svn]
  Still image: python image_to_svn.py image.png   [output.svn]

VideoPlayer chain (N frames):
  Button → Timer_0
  Timer_i → [MC_0..MC_139 for frame i]  +  Timer_{(i+1) % N}
  MC_j_i  -> Monitor_j  (pushes 6x2 pixel text of frame i)

Screen resolution : 42x40 pixels  (7 cols x 20 rows, each monitor = 6x2 px)
UniqueID formula  : float32(float32(x)^2 + float32(y)^2 + float32(z)^2)  (verified from game saves)
"""

import json, sys, os, time, struct
from PIL import Image

# ── Configurable ──────────────────────────────────────────────────────────────
MAX_FRAMES     = 20       # max frames extracted from GIF
TIMER_INTERVAL = 1     # seconds per frame

# ── Screen layout ─────────────────────────────────────────────────────────────
PIX_W = 6   # pixels per monitor horizontally
PIX_H = 2   # pixels per monitor vertically

MON_COLS = 20    # monitor columns  →  image width  = MON_COLS * PIX_W = 42
MON_ROWS = 20   # monitor rows     →  image height = MON_ROWS * PIX_H = 40

IMG_W = MON_COLS * PIX_W   # 42
IMG_H = MON_ROWS * PIX_H   # 40

# ── World space (from original saves) ────────────────────────────────────────
MIN_Y    = 0.53147
STEP_X   = 1.73
STEP_Y   = 1.06
START_X  = -(MON_COLS * STEP_X + 5.0)
Z_SCREEN = 15.0

ROT_FACE = {"x": 0.0, "y": 1.0, "z": 0.0, "w": 5.043734e-09}
ROT_CTRL = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}

# ── Controller positions ──────────────────────────────────────────────────────
CTRL_X     = -200.0
CTRL_Y     = 0.53
CTRL_Z_START = 1.0
CTRL_Z_STEP  = 1.0

def ctrl_pos(index):
    return CTRL_X, CTRL_Y, CTRL_Z_START + index * CTRL_Z_STEP


# ── UniqueID ──────────────────────────────────────────────────────────────────

def _f32(v):
    return struct.unpack('f', struct.pack('f', v))[0]

def uid(x, y, z):
    fx, fy, fz = _f32(x), _f32(y), _f32(z)
    xx = _f32(fx * fx)
    yy = _f32(fy * fy)
    zz = _f32(fz * fz)
    return _f32(_f32(xx + yy) + zz)


# ── Color helpers ─────────────────────────────────────────────────────────────

def quantize(v):
    return round(v / 255 * 15) * 17

def to_hex(r, g, b):
    return f"#{quantize(r)//17:X}{quantize(g)//17:X}{quantize(b)//17:X}"


# ── Monitor text (6×2 pixel block) ───────────────────────────────────────────

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


# ── Per-monitor pixel text for a frame ───────────────────────────────────────

def frame_monitor_texts(img):
    pixels = img.load()
    texts  = []
    colors = []

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

            from collections import Counter
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

    IDX_BTN    = 0
    IDX_TMR    = lambda fi: 1 + fi
    IDX_MC     = lambda fi, mi: 1 + n + fi * n_monitors + mi

    frame0_texts, frame0_colors = frame_monitor_texts(frames[0])

    monitor_uids = []
    for row in range(MON_ROWS):
        for col in range(MON_COLS):
            idx = row * MON_COLS + col
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
                    "Text": frame0_texts[idx],
                    "Color": frame0_colors[idx]
                }
            })

    mc_uid_grid = []
    for fi in range(n):
        row_uids = []
        for mi in range(n_monitors):
            x, y, z = ctrl_pos(IDX_MC(fi, mi))
            row_uids.append(uid(x, y, z))
        mc_uid_grid.append(row_uids)

    timer_uid_list = [uid(*ctrl_pos(IDX_TMR(fi))) for fi in range(n)]
    btn_uid        = uid(*ctrl_pos(IDX_BTN))

    bx, by, bz = ctrl_pos(IDX_BTN)
    props.append({
        "name": "Button",
        "uniqueId": btn_uid,
        "position": {"x": bx, "y": by, "z": bz},
        "rotation": ROT_CTRL,
        "isKinematic": True,
        "instantiationData": {"Toggle": False},
        "runtimeData": {
            "connectedIds": [timer_uid_list[0]],
            "Signal": False
        }
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
            "runtimeData": {
                "connectedIds": connected
            }
        })

    for fi in range(n):
        frame_texts, frame_colors = frame_monitor_texts(frames[fi])
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
                "runtimeData": {
                    "connectedIds": [monitor_uids[mi]]
                }
            })

    return {"map": "FlatGrass", "props": props}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  GIF:   python image_to_svn.py animation.gif [output.svn]")
        print("  Still: python image_to_svn.py image.png     [output.svn]")
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
    print(f"Image   : {IMG_W}x{IMG_H} px  ({MON_COLS}x{MON_ROWS} monitors, {PIX_W}x{PIX_H} px/monitor)")

    print("Building save... ", end="", flush=True)
    data = build_save(frames)
    print("done")

    mon_count   = MON_COLS * MON_ROWS
    mc_count    = mon_count * n
    total_props = len(data["props"])
    print(f"Monitors: {mon_count}  |  MCs: {mc_count}  |  Timers: {n}  |  Total props: {total_props}")

    if output_path is None:
        ts = int(time.time() * 1000)
        output_path = os.path.join(os.path.dirname(os.path.abspath(input_path)),
                                   f"hypper_{ts}.svn")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Output  : {output_path}")


if __name__ == "__main__":
    main()