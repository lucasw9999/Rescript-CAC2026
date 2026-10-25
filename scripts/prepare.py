#!/usr/bin/env python3
"""Stage 1: set up a work dir, transcribe with word timestamps, grab frames, list voice-reference candidates.

usage: python3 prepare.py <video> <workdir> [--frames-every 20]

Writes into <workdir>:
  in.mov            symlink to the original (never modified)
  a16f.wav          16 kHz mono float audio
  words.json        [[start, end, word, prob], ...]  (whisper-large-v3-turbo, MLX)
  transcript.txt    indexed transcript, "<gap>" markers for pauses > 0.6 s
  frames/f<sec>.jpg one frame every N seconds, for reading slide text
  ref_candidates.txt fluent 10-18 s spans to clone the voice from
"""
import argparse, json, os, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("workdir")
ap.add_argument("--frames-every", type=int, default=20)
a = ap.parse_args()

os.makedirs(a.workdir, exist_ok=True)
src = os.path.abspath(a.video)
link = os.path.join(a.workdir, "in.mov")
if os.path.lexists(link): os.remove(link)
os.symlink(src, link)
os.chdir(a.workdir)

def run(*cmd): subprocess.run(cmd, check=True)

def probe(sel, entry):
    # JSON, not csv: csv adds an empty column when the stream has side data (rotation etc.), e.g. "0.000000,"
    st = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries",
                                             f"stream={entry}", "-of", "json", "in.mov"]))["streams"]
    return st[0].get(entry, "") if st else ""
def start(sel):
    out = probe(sel, "start_time")
    return float(out) if out not in ("", "N/A") else 0.0
# put audio on the video's timeline: QuickTime can start the mic track seconds after the picture
off = start("a:0") - start("v:0")
align = f"adelay={int(round(off * 1000))}:all=1" if off > 0.005 else (f"atrim=start={-off:.3f}" if off < -0.005 else "anull")
run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "in.mov", "-map", "0:a:0",
    "-af", f"asetpts=PTS-STARTPTS,{align}", "-ac", "1", "-ar", "16000", "-c:a", "pcm_f32le", "a16f.wav")
# video-stream duration: the audio track can outlast the picture
dur = float(probe("v:0", "duration"))

import mlx_whisper
r = mlx_whisper.transcribe("a16f.wav", path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
                           word_timestamps=True, language="en", condition_on_previous_text=False)
W = [(float(w["start"]), float(w["end"]), w["word"], float(w.get("probability", 0)))
     for s in r["segments"] for w in s["words"]]
json.dump(W, open("words.json", "w"))

out, prev = [], 0.0
for i, (s, e, t, p) in enumerate(W):
    if s - prev > 0.6: out.append(f"\n<{s - prev:.1f}s>[{s:.1f}] ")
    out.append(f"{i}:{t.strip()} ")
    prev = e
open("transcript.txt", "w").write("".join(out).strip() + "\n")

os.makedirs("frames", exist_ok=True)
for t in range(2, int(dur), a.frames_every):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", "in.mov",
                    "-frames:v", "1", "-vf", "scale=1100:-1", "-pix_fmt", "yuvj420p", f"frames/f{t:04d}.jpg"])  # best effort

# Voice-reference candidates: 10-18 s runs of words with few low-confidence words. The ideal clip has no internal
# gap > 0.35 s and starts and ends on a sentence; casual speakers pause more than that, so the rules relax step by
# step until something qualifies (smallest total pause wins), rather than leaving nothing to clone from.
def candidates(max_gap, sentences, lo, hi):
    out = []
    for i in range(len(W)):
        if sentences and i and not W[i - 1][2].strip().endswith((".", "?", "!")): continue
        for j in range(i + 1, len(W)):
            if W[j][0] - W[j - 1][1] > max_gap: break
            L = W[j][1] - W[i][0]
            if L > hi: break
            if L >= lo and (not sentences or W[j][2].strip().endswith((".", "?", "!"))):
                low = sum(1 for w in W[i:j + 1] if w[3] < 0.5)
                gaps = sum(W[k][0] - W[k - 1][1] for k in range(i + 1, j + 1))
                out.append((low, round(gaps, 2), -L, i, j))
    return sorted(out)
for rules in [(0.35, True, 10, 18), (0.6, True, 10, 18), (0.6, False, 10, 18), (1.0, False, 10, 18), (1.5, False, 8, 20)]:
    cands = candidates(*rules)
    if cands: break
with open("ref_candidates.txt", "w") as f:
    for low, gaps, nl, i, j in cands[:8]:
        f.write(f"words {i}-{j}  {W[i][0]:.2f}-{W[j][1]:.2f}s ({-nl:.1f}s, {low} low-conf, {gaps:.1f}s of pauses): "
                + " ".join(w[2].strip() for w in W[i:j + 1]) + "\n")

print(f"duration {dur:.1f}s, {len(W)} words, {len(os.listdir('frames'))} frames, "
      f"{min(len(cands), 8)} ref candidates -> {os.getcwd()}")
