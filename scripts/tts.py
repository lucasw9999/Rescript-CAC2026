#!/usr/bin/env python3
"""Stage 3: speak each script unit in the cloned voice, then verify by transcribing it back.

usage: python3 tts.py <workdir> "<verbatim transcript of ref.wav>" [unit,unit,...]

Reads <workdir>/script.json, writes <workdir>/tts/uNN.wav, prints a verification table
and saves it as tts/verify.json. Units whose back-transcription similarity < 0.9 are
listed as SUSPECT: read the WANT/GOT pair. Digit formatting ("3,300" vs "three thousand
three hundred") is harmless; merged sentences, dropped or invented words are not, so
reword and regenerate just those.
"""
import json, os, re, sys, difflib, numpy as np
from scipy.io import wavfile

wd, ref_text = sys.argv[1], sys.argv[2]
os.chdir(wd); os.makedirs("tts", exist_ok=True)
S = json.load(open("script.json"))
text = lambda u: u["text"] if isinstance(u, dict) else u[2]
idx = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else range(len(S))

from mlx_audio.tts.utils import load_model
model = load_model("mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")
for i in idx:
    res = list(model.generate(text=text(S[i]), ref_audio="ref.wav", ref_text=ref_text,
                              temperature=0.7, top_p=0.9))
    a = np.concatenate([np.array(r.audio) for r in res]).astype(np.float32)
    wavfile.write(f"tts/u{i:02d}.wav", model.sample_rate, a)
    print(f"u{i:02d} {len(a) / model.sample_rate:5.1f}s", flush=True)
del model

import mlx_whisper
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
def say(n):
    """12 -> "twelve", 45 -> "forty five", 3300 -> "three thousand three hundred": digits and words compare equal."""
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000: return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + say(n % 100))
    if n < 1000000: return say(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + say(n % 1000))
    return str(n)
def norm(s):
    s = re.sub(r"(\d),(\d{3})", r"\1\2", s.lower().replace("-", " ").replace("%", " percent"))
    s = re.sub(r"\d+", lambda m: " " + say(int(m.group(0))) + " ", s)
    return re.sub(r"[^a-z ]", " ", s).split()
bad, checks = [], []
for i in idx:
    got = mlx_whisper.transcribe(f"tts/u{i:02d}.wav", language="en",
                                 path_or_hf_repo="mlx-community/whisper-large-v3-turbo")["text"]
    r = difflib.SequenceMatcher(None, norm(text(S[i])), norm(got)).ratio()
    checks.append({"unit": i, "ratio": round(r, 3), "want": text(S[i]), "got": got.strip()})
    if r < 0.9:
        bad.append(i); print(f"SUSPECT u{i:02d} {r:.2f}\n  WANT: {text(S[i])}\n  GOT : {got.strip()}")
json.dump(checks, open("tts/verify.json", "w"), indent=1)  # this run's units only
print("suspect units:", bad or "none")
