#!/usr/bin/env python3
"""Pass 1: find the macOS cursor in every frame (arrow and I-beam).

The macOS cursor body is pure black (<=12) while UI text is dark gray (>=21), so cursor
candidates are small pure-black blobs. Each blob is scored against binary body templates:
score = (fraction of template body that is black) - (fraction of the ring around it that is
black); a real cursor has a white rim, so it scores ~1, glyphs/black areas score ~0.

usage: python3 cursor_detect.py <video> <templates.npz> <out.json> [seconds]
  seconds: only scan the first N seconds (e.g. stop where a live demo starts)
"""
import cv2, numpy as np, subprocess, sys, json, time

video, tpath, out = sys.argv[1:4]
DUR = sys.argv[4] if len(sys.argv) > 4 else None
_st = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                         "stream=width,height", "-of", "json", video]))["streams"][0]   # json: csv breaks on side data
W, H = int(_st["width"]), int(_st["height"])
Z = np.load(tpath, allow_pickle=True)
TPL = []
for name in Z["names"]:
    body = Z[f"{name}_body"].astype(np.float32)
    ring = cv2.dilate(body.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2).astype(np.float32) - body
    TPL.append((str(name), body, ring, body.sum(), ring.sum(), tuple(Z[f"{name}_tip"])))
areas = [t[3] for t in TPL]
AMIN, AMAX = 0.5 * min(areas), 1.6 * max(areas)

p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, *(["-t", DUR] if DUR else []), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                     stdout=subprocess.PIPE, bufsize=W * H * 4)
res = []; fi = 0; t0 = time.time()
while True:
    buf = p.stdout.read(W * H)
    if len(buf) < W * H: break
    g = np.frombuffer(buf, np.uint8).reshape(H, W)
    B = (g <= 12).astype(np.uint8); B[:6] = 0; B[-6:] = 0; B[:, :6] = 0; B[:, -6:] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(B, connectivity=8)
    best = None
    for k in range(1, n):
        x, y, w, h, a = st[k]
        if not (AMIN <= a <= AMAX) or w > 60 or h > 80: continue
        x0, y0 = max(0, x - 8), max(0, y - 8)
        win = B[y0:min(H, y + h + 8), x0:min(W, x + w + 8)].astype(np.float32)
        for name, body, ring, bs, rs, tip in TPL:
            if win.shape[0] < body.shape[0] or win.shape[1] < body.shape[1]: continue
            sb = cv2.matchTemplate(win, body, cv2.TM_CCORR) / bs
            sr = cv2.matchTemplate(win, ring, cv2.TM_CCORR) / rs
            s = sb - sr
            _, mx, _, loc = cv2.minMaxLoc(s)
            if best is None or mx > best[0]:
                best = (float(mx), name, int(x0 + loc[0]), int(y0 + loc[1]), int(x0 + loc[0] + tip[0]), int(y0 + loc[1] + tip[1]))
    res.append(best if best and best[0] > 0.55 else None)
    fi += 1
    if fi % 1500 == 0: print(f"{fi} frames {time.time() - t0:.0f}s", flush=True)
json.dump({"W": W, "H": H, "frames": res}, open(out, "w"))
found = sum(r is not None for r in res)
print(f"done {fi} frames, cursor found in {found} ({100 * found / max(fi, 1):.1f}%), {time.time() - t0:.0f}s")
