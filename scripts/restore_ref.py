#!/usr/bin/env python3
"""Stage 2: cut the voice-reference span and restore it to studio quality with Sidon
(denoise + dereverb + 48 kHz bandwidth restoration; preserves speaker identity).

usage: python3 restore_ref.py <workdir> <start_s> <end_s>
Writes <workdir>/ref.wav (24 kHz mono, what Qwen3-TTS wants).

Sidon runs ~5x real time on CPU. Pass --full to also restore the whole track
(sidon48.wav), only needed if you want a real-voice version too.
"""
import os, subprocess, sys, numpy as np
from scipy.io import wavfile

wd, s, e = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
full = "--full" in sys.argv
os.chdir(wd)

import onnxruntime as ort
from huggingface_hub import hf_hub_download
from transformers import AutoFeatureExtractor
R = "soniqo/Sidon-ONNX"
prov = ["CPUExecutionProvider"]
pred = ort.InferenceSession(hf_hub_download(R, "fp32/sidon-predictor.onnx"), providers=prov)
voc = ort.InferenceSession(hf_hub_download(R, "fp32/sidon-vocoder.onnx"), providers=prov)
fe = AutoFeatureExtractor.from_pretrained("facebook/w2v-bert-2.0")

def restore(a):
    """16 kHz float mono -> 48 kHz restored. 20 s chunks, 1 s linear crossfade."""
    a = a / (np.abs(a).max() + 1e-9) * 0.9
    CH, OV = 20 * 16000, 16000
    out = np.zeros(len(a) * 3, np.float32); ws = np.zeros_like(out); pos = 0
    while True:
        seg = a[pos:pos + CH]
        f = fe(seg, sampling_rate=16000, return_tensors="np")["input_features"].astype(np.float32)
        y = voc.run(None, {"features": pred.run(None, {"input_features": f})[0]})[0].reshape(-1)[:len(seg) * 3]
        w = np.ones(len(y), np.float32); r = OV * 3
        if pos > 0: w[:r] = np.linspace(0, 1, r)
        if pos + CH < len(a) and len(y) > r: w[-r:] = np.linspace(1, 0, r)
        o = pos * 3; out[o:o + len(y)] += y * w; ws[o:o + len(y)] += w
        if pos + CH >= len(a): break
        pos += CH - OV
    return out / np.maximum(ws, 1e-6)

sr, a = wavfile.read("a16f.wav"); a = a.astype(np.float32)
y = restore(a[int((s - 0.2) * sr):int((e + 0.25) * sr)])
wavfile.write("ref48.wav", 48000, y.astype(np.float32))
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", "ref48.wav",
                "-ar", "24000", "-ac", "1", "ref.wav"], check=True)
print("ref.wav", len(y) / 48000, "s")
if full:
    wavfile.write("sidon48.wav", 48000, restore(a).astype(np.float32))
    print("sidon48.wav written")
