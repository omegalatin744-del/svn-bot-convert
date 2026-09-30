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


if name == "main":
    main()
