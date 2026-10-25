#!/usr/bin/env python3
"""Erase the cursor from the frames listed in det.json (frames past the list are untouched).

Fill order for each frame's cursor footprint:
  0. the scene's clean plate: per-pixel median of the scene's frames with the cursor masked
     out (best for slides: rock-steady, the same pixels every frame);
  1. the nearest frame where the same spot is uncovered (page static, cursor elsewhere);
  2. the same content shifted vertically (page scrolled; masked template match on a strip);
  3. cv2.inpaint.
While the cursor rests (a "group"), the previous frame's patch is reused as long as its
surroundings still match, so the erased spot can never shimmer.

usage: python3 cursor_erase.py <video> <templates.npz> <det.json> <out.mp4>
"""
import cv2, numpy as np, subprocess, sys, json, time

video, tpath, dpath, out = sys.argv[1:5]
Z = np.load(tpath, allow_pickle=True)
BODY = {str(n): Z[f"{n}_body"].astype(np.uint8) for n in Z["names"]}
D = json.load(open(dpath)); W, H = D["W"], D["H"]; DET = D["frames"]; N = len(DET)
DIL, MARGIN, WIN, MAXC = 6, 12, 90, 60
IN_CS = "scale=in_color_matrix=bt709:in_range=tv"

def footprint(det):
    _, name, x, y = det[:4]; b = BODY[name]
    y0, y1 = max(0, y - DIL - MARGIN), min(H, y + b.shape[0] + DIL + 2 + MARGIN)
    x0, x1 = max(0, x - DIL - MARGIN), min(W, x + b.shape[1] + DIL + 2 + MARGIN)
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    m[y - y0:y - y0 + b.shape[0], x - x0:x - x0 + b.shape[1]] = b
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * DIL + 1, 2 * DIL + 1)))
    m = np.maximum(m, np.roll(m, 2, axis=0))
    return (y0, y1, x0, x1), m.astype(bool)

def cursor_rows(det, x0, x1):
    """rows [a,b) covered by the cursor at a frame, if it intersects columns [x0,x1)."""
    if det is None: return None
    (cy0, cy1, cx0, cx1), _ = footprint(det)
    return None if (cx1 <= x0 or cx0 >= x1) else (cy0, cy1)

def near_ring(m):
    return cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(bool) & ~m

def ok(cand, cur, nr):
    d = np.abs(cand.astype(np.int16) - cur.astype(np.int16)).max(axis=2)[nr]
    return d.mean() < 2.0 and (d > 20).mean() < 0.005

groups = []
for i, d in enumerate(DET):
    if d is None: continue
    key = (d[1], d[2], d[3])
    if groups and groups[-1]["key"] == key and groups[-1]["end"] == i - 1: groups[-1]["end"] = i
    else: groups.append({"key": key, "start": i, "end": i, "det": d})

# pass S: scene cuts from 1/8-scale thumbnails, ignoring the cursor itself
TS = 8; tw, th = W // TS, H // TS
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", f"{IN_CS},scale={tw}:{th}", "-frames:v", str(N),
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
def tmask(det):
    mk = np.ones((th, tw), bool)
    if det is not None:
        (y0, y1, x0, x1), _ = footprint(det); mk[y0 // TS:y1 // TS + 1, x0 // TS:x1 // TS + 1] = False
    return mk
scene = [0] * N; prev = None; sid = 0
for i in range(N):
    b = dec.stdout.read(tw * th)
    if len(b) < tw * th: break
    g = np.frombuffer(b, np.uint8).astype(np.float32).reshape(th, tw)
    if prev is not None:
        mk = tmask(DET[i]) & tmask(DET[i - 1])
        if np.abs(g - prev)[mk].mean() > 1.5: sid += 1
    scene[i] = sid; prev = g
dec.kill()
scenes = {}
for i, s_ in enumerate(scene): scenes.setdefault(s_, []).append(i)
plan = {}   # scene -> (bbox, sample frame set)
for s_, fr in scenes.items():
    dets = [DET[i] for i in fr if DET[i] is not None]
    if len(fr) < 8 or not dets: continue
    regs = [footprint(d)[0] for d in dets]
    bb = (min(r[0] for r in regs), max(r[1] for r in regs), min(r[2] for r in regs), max(r[3] for r in regs))
    step = max(1, len(fr) // 40)
    plan[s_] = (bb, set(fr[::step]))
samples = {s_: [] for s_ in plan}; plates = {}
print(f"{sid + 1} scenes, plates planned for {len(plan)}", flush=True)

# pass A: nearest uncovered frame before/after each group, up to 15 s away
def overlaps(det, reg):
    if det is None: return False
    (cy0, cy1, cx0, cx1), _ = footprint(det); y0, y1, x0, x1 = reg
    return not (cx1 <= x0 or cx0 >= x1 or cy1 <= y0 or cy0 >= y1)
OFFS = [1, 15, 45, 90, 180, 300, 450]
for g in groups:
    g["reg"], g["m"] = footprint(g["det"]); g["past"] = g["fut"] = None; g["strips"] = []
    g["want"] = set()
    if g["end"] - g["start"] >= 30:
        g["want"] = {g["start"] - o for o in OFFS if g["start"] - o >= 0} | {g["end"] + o for o in OFFS if g["end"] + o < N}
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", IN_CS, "-frames:v", str(N),
                        "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, bufsize=W * H * 6)
lo = 0
for i in range(N):
    buf = dec.stdout.read(W * H * 3)
    if len(buf) < W * H * 3: break
    F = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    s_ = scene[i]
    if s_ in plan and i in plan[s_][1]:
        (y0, y1, x0, x1) = plan[s_][0]; c = F[y0:y1, x0:x1].astype(np.float32)
        if DET[i] is not None:
            (fy0, fy1, fx0, fx1), fm = footprint(DET[i]); c = c.copy()
            sub = c[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]; sub[fm] = np.nan
        samples[s_].append(c)
    if s_ in plan and i == scenes[s_][-1] and samples[s_]:
        st = np.stack(samples[s_]); med = np.nanmedian(st, axis=0)
        plates[s_] = (plan[s_][0], np.nan_to_num(med).clip(0, 255).astype(np.uint8), ~np.isnan(med).any(axis=2))
        samples[s_] = None
    while lo < len(groups) and i > groups[lo]["end"] + 450: lo += 1
    for g in groups[lo:]:
        if g["start"] > i + 450: break
        if i in g["want"]:
            y0_, y1_, x0_, x1_ = g["reg"]; g["strips"].append((i, F[:, x0_:x1_].copy()))
        if overlaps(DET[i], g["reg"]): continue
        y0, y1, x0, x1 = g["reg"]
        if i < g["start"]: g["past"] = F[y0:y1, x0:x1].copy()
        elif i > g["end"] and g["fut"] is None: g["fut"] = F[y0:y1, x0:x1].copy()
dec.kill(); print("pass A done", flush=True)

INP = []; patches = {}; stats = {"plate": 0, "static": 0, "shift": 0, "inpaint": 0, "reuse": 0}; t0 = time.time()
for gi, g in enumerate(groups):
    (y0, y1, x0, x1), m = footprint(g["det"]); h, w = y1 - y0, x1 - x0; ring = ~m; nr = near_ring(m)
    a, b = max(0, g["start"] - WIN), min(N, g["end"] + WIN + 1)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a / 30:.4f}", "-i", video, "-frames:v", str(b - a),
                          "-vf", f"{IN_CS},crop={w}:{H}:{x0}:0", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True, check=True).stdout
    S = np.frombuffer(raw, np.uint8).reshape(-1, H, w, 3); b = a + len(S)
    G = S.mean(axis=3).astype(np.float32)
    last = None
    for i in range(g["start"], g["end"] + 1):
        if not (a <= i < b): continue
        cur = S[i - a, y0:y1]; curg = G[i - a, y0:y1]
        if last is not None and ok(last, cur, nr):            # resting: reuse the exact same pixels
            patches[i] = (y0, x0, m, last); stats["reuse"] += 1; continue
        fill = None
        pl = plates.get(scene[i])
        if pl is not None:
            (py0, py1, px0, px1), img, valid = pl
            if py0 <= y0 and y1 <= py1 and px0 <= x0 and x1 <= px1:
                cand = img[y0 - py0:y1 - py0, x0 - px0:x1 - px0]; vm = valid[y0 - py0:y1 - py0, x0 - px0:x1 - px0]
                if vm[m].all() and ok(cand, cur, nr): fill = cand; stats["plate"] += 1
        for d in ((g["past"], g["fut"]) if fill is None else ()):
            if d is not None and ok(d, cur, nr): fill = d; stats["static"] += 1; break
        order = sorted((j for j in range(a, b) if j != i), key=lambda j: abs(j - i))[:MAXC]
        for j in (order if fill is None else []):   # 1. static: same rows, cursor elsewhere
            r = cursor_rows(DET[j] if j < N else None, x0, x1)
            if r and not (r[1] <= y0 or r[0] >= y1): continue
            if ok(S[j - a, y0:y1], cur, nr):
                fill = S[j - a, y0:y1]; stats["static"] += 1; break
        if fill is None:                      # 2. scrolled: find the rows by template match
            tm = nr.astype(np.float32)
            outside = sorted((j for j in range(a, b) if j < g["start"] or j > g["end"]), key=lambda j: abs(j - i))
            for j in (outside[:20] + order[:10]):
                res = cv2.matchTemplate(G[j - a], curg, cv2.TM_SQDIFF, mask=tm) / nr.sum()
                r = cursor_rows(DET[j] if j < N else None, x0, x1)
                if r:  # forbid positions where the cursor itself is at frame j
                    res[max(0, r[0] - h):r[1]] = 1e9
                res[max(0, y0 - 2):y0 + 3] = 1e9  # dy~0 already tried as static
                mn, _, loc, _ = cv2.minMaxLoc(res)
                yy = loc[1]
                if mn < 6.0 and ok(S[j - a, yy:yy + h], cur, nr):
                    fill = S[j - a, yy:yy + h]; stats["shift"] += 1; break
        if fill is None:
            tm = nr.astype(np.float32)
            for j, strip in sorted(g["strips"], key=lambda t: abs(t[0] - i)):
                sg = strip.mean(axis=2).astype(np.float32)
                res = cv2.matchTemplate(sg, curg, cv2.TM_SQDIFF, mask=tm) / nr.sum()
                r = cursor_rows(DET[j] if j < N else None, x0, x1)
                if r: res[max(0, r[0] - h):r[1]] = 1e9
                mn, _, loc, _ = cv2.minMaxLoc(res); yy = loc[1]
                if mn < 6.0 and ok(strip[yy:yy + h], cur, nr):
                    fill = strip[yy:yy + h]; stats["shift"] += 1; break
        if fill is not None:
            p = cur.copy(); p[m] = fill[m]
        else:
            p = cv2.inpaint(np.ascontiguousarray(cur), m.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
            stats["inpaint"] += 1; INP.append(i)
        patches[i] = (y0, x0, m, p); last = p
    if gi % 40 == 0: print(f"group {gi}/{len(groups)} {time.time() - t0:.0f}s {stats}", flush=True)
print("patches", stats); json.dump(INP, open("cursor_inpaint_frames.json", "w"))

enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
    "-r", "30", "-i", "-", "-i", video, "-map", "0:v", "-map", "1:a",
    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy", "-movflags", "+faststart",
    "-shortest", out], stdin=subprocess.PIPE)
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", IN_CS, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       stdout=subprocess.PIPE, bufsize=W * H * 6)
i = 0
while True:
    buf = dec.stdout.read(W * H * 3)
    if len(buf) < W * H * 3: break
    if i in patches:
        F = np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()
        y0, x0, m, p = patches[i]; F[y0:y0 + p.shape[0], x0:x0 + p.shape[1]] = p
        buf = F.tobytes()
    enc.stdin.write(buf); i += 1
enc.stdin.close(); enc.wait()
print("done", i, "frames", f"{time.time() - t0:.0f}s")
