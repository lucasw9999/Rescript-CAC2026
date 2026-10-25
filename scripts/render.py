#!/usr/bin/env python3
"""Stage 4: lay the narration end to end and retime each unit's video span to fit it.

usage: python3 render.py <workdir> <output.mp4> [--breaks 3,8,11]

script.json units come in two forms:
  [w0, w1, "text"]                          words w0..w1 of in.mov
  {"words": [w0, w1], "text": ..., "end": t} same, but the video span stops at t
                                             (use it to cut a broken tail, e.g. an error page)
  {"src": "/abs/other.mov", "start": s, "end": e, "text": ...}
                                             span s..e of another recording (splice in a
                                             better take of a demo); scaled/padded to in.mov's size

A word unit's span runs from just before its first word to just before the next word
unit's first word (unit 0 starts 1 s before the first word; a final word unit ends 2 s
after its last word), so every on-screen action stays, sped up or slowed to fit.
--breaks lists unit indices that open a new section; they get an extra 0.35 s of silence.
--pace slows the narration (0.92 by default, a little calmer than the voice model) and --pause sets the gap
between lines (0.6 s).
"""
import argparse, json, os, subprocess, numpy as np
from scipy.io import wavfile

ap = argparse.ArgumentParser()
ap.add_argument("workdir"); ap.add_argument("output")
ap.add_argument("--breaks", default="")
ap.add_argument("--pace", type=float, default=0.92, help="narration speed: below 1 is slower (time-stretched, same pitch)")
ap.add_argument("--pause", type=float, default=0.6, help="seconds of silence between lines")
a = ap.parse_args()
out = os.path.abspath(a.output)
os.chdir(a.workdir)

def probe(path, entry):
    # JSON, not csv: csv adds an empty column when the stream has side data (rotation etc.), e.g. "1440,900,"
    st = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                             f"stream={entry}", "-of", "json", path]))["streams"][0]
    return ",".join(str(st.get(k, "")) for k in entry.split(","))

S = json.load(open("script.json")); W = json.load(open("words.json"))
U = [u if isinstance(u, dict) else {"words": u[:2], "text": u[2]} for u in S]
BREAK = {int(x) for x in a.breaks.split(",") if x}
# video-stream duration, not container: audio can outlast the picture
VEND = float(probe("in.mov", "duration"))
WID, HGT = probe("in.mov", "width,height").split(",")
sources = ["in.mov"] + sorted({u["src"] for u in U if "src" in u})

SR = 24000; PAUSE = a.pause

def stretch(x, pace):
    """Slow down (pace < 1) or speed up a line without changing its pitch. The voice model's own speed option is a no-op."""
    if abs(pace - 1) < 1e-3: return x
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0",
                          "-af", f"atempo={pace}", "-f", "f32le", "-ar", str(SR), "-ac", "1", "pipe:1"],
                         input=x.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(out, np.float32)
clips, segs = [], []
for i, u in enumerate(U):
    sr, x = wavfile.read(f"tts/u{i:02d}.wav"); x = x.astype(np.float32)
    nz = np.nonzero(np.abs(x) > 0.01)[0]
    x = x[max(0, nz[0] - int(.05 * SR)):nz[-1] + int(.12 * SR)]          # trim TTS silence
    x = stretch(x, a.pace)
    pre = 0.3 if i == 0 else 0
    post = 1.0 if i == len(U) - 1 else PAUSE + (0.35 if i + 1 in BREAK else 0)
    clip = np.concatenate([np.zeros(int(pre * SR)), x, np.zeros(int(post * SR))]).astype(np.float32)
    clips.append(clip)
    if "src" in u:
        src, vs, ve = sources.index(u["src"]), u["start"], u["end"]
    else:
        w0 = u["words"][0]
        vs = max(0.0, W[w0][0] - 1.0) if i == 0 else W[w0][0] - 0.15
        nxt = U[i + 1] if i + 1 < len(U) else None
        if "end" in u: ve = u["end"]
        elif nxt and "words" in nxt: ve = W[nxt["words"][0]][0] - 0.15
        else: ve = min(VEND, W[u["words"][1]][1] + 2.0)
        src = 0
    segs.append((src, vs, ve, len(clip) / SR))
wavfile.write("narr24.wav", SR, np.concatenate(clips))
json.dump(segs, open("segs.json", "w"))

na = len(sources)  # narration is input index na
# fps=30 BEFORE trim: screen recordings are VFR (often <10 fps on static screens), and
# trimming VFR overshoots each cut by up to one source frame gap, drifting seconds over a talk
parts = [f"[{s}:v]fps=30,trim=start={vs:.3f}:end={ve:.3f},setpts=(PTS-STARTPTS)*{d / (ve - vs):.6f},"
         f"scale={WID}:{HGT}:force_original_aspect_ratio=decrease,pad={WID}:{HGT}:(ow-iw)/2:(oh-ih)/2,"
         f"setsar=1,fps=30,format=yuv420p[v{i}]" for i, (s, vs, ve, d) in enumerate(segs)]
fc = (";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(segs)))
      + f"concat=n={len(segs)}:v=1:a=0,tpad=stop_mode=clone:stop_duration=3[vout];"
      f"[{na}:a]aresample=48000,highpass=f=70,"
      "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150:makeup=2,"
      "loudnorm=I=-16:TP=-1.5:LRA=9[aout]")
open("fc.txt", "w").write(fc)
inputs = sum((["-i", p] for p in sources), []) + ["-i", "narr24.wav"]
# ffmpeg >= 7: filter script is "-/filter_complex <file>" (-filter_complex_script was removed)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
                "-/filter_complex", "fc.txt", "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", "-shortest", out], check=True)

t = 0.0
for i, (s, vs, ve, d) in enumerate(segs):
    print(f"u{i:02d} out {t:6.1f}s  src{s} {vs:6.1f}-{ve:6.1f}  speed x{(ve - vs) / d:4.2f}")
    if (ve - vs) / d > 3:
        print(f"  ^ WARNING x{(ve - vs) / d:.1f}: long silent stretch in this span; look at its frames. "
              "If the screen is doing something worth seeing, give that action its own short line.")
    t += d
print(f"wrote {out}  ({t:.1f}s, from {VEND:.1f}s)")
