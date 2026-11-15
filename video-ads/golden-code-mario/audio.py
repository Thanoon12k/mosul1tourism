"""Original 8-bit soundtrack + SFX synced to scene.html timings. Writes audio.wav (30s)."""
import wave
import numpy as np

SR, DUR = 44100, 30.0
out = np.zeros(int(SR * DUR))


def tone(f, d, vol=0.18, duty=0.5, kind="sq"):
    t = np.arange(int(SR * d)) / SR
    if kind == "sq":
        w = np.where((t * f) % 1 < duty, 1.0, -1.0)
    elif kind == "tri":
        w = 2 * np.abs(2 * ((t * f) % 1) - 1) - 1
    else:
        w = np.random.uniform(-1, 1, len(t))
    env = np.minimum(1, np.minimum(t / 0.005, (d - t) / 0.02 + 0.001))
    return w * env * vol


def put(at, sig):
    i = int(at * SR)
    j = min(len(out), i + len(sig))
    if i < len(out):
        out[i:j] += sig[: j - i]


def sweep(at, f0, f1, d, vol=0.15):
    t = np.arange(int(SR * d)) / SR
    f = f0 + (f1 - f0) * t / d
    ph = np.cumsum(f) / SR
    put(at, np.where(ph % 1 < 0.5, 1.0, -1.0) * vol * (1 - t / d))


N = lambda n: 440 * 2 ** ((n - 69) / 12)  # midi -> Hz
# intro jingle
for k, n in enumerate([72, 76, 79, 84, 79, 84]):
    put(0.3 + k * 0.14, tone(N(n), 0.13, 0.16))
# main loop (original melody), 150 bpm eighths
beat = 0.2
mel = [76, 0, 79, 81, 79, 76, 72, 74, 76, 0, 76, 79, 81, 84, 81, 79, 77, 0, 77, 81, 79, 77, 76, 74, 72, 74, 76, 79, 76, 0, 72, 0]
bass = [48, 55, 48, 55, 53, 60, 53, 60, 45, 52, 45, 52, 43, 50, 43, 50]


def music(t0, t1, transpose=0, under=False):
    t, k = t0, 0
    while t < t1:
        n = mel[k % len(mel)]
        if n and not under:
            put(t, tone(N(n + transpose), beat * 0.9, 0.09, 0.25))
        b = bass[(k // 2) % len(bass)] + transpose - (12 if under else 0)
        if k % 2 == 0:
            put(t, tone(N(b), beat * 1.8, 0.14 if under else 0.12, kind="tri"))
        if not under and k % 4 == 2:
            put(t, tone(0, 0.04, 0.05, kind="noise"))
        t += beat
        k += 1


music(2.2, 14.8)
music(15.0, 18.0, under=True)
for k, n in enumerate([60, 67, 72, 67, 60, 72]):  # underground stabs
    put(15.0 + k * 0.5, tone(N(n), 0.12, 0.08, 0.125))
music(18.0, 25.4, transpose=2)
# SFX
for j in [4.65, 6.25, 7.85, 9.45, 13.3, 19.15, 21.15, 25.2]:
    sweep(j, 300, 900, 0.18, 0.1)
for h in [5.0, 6.6, 8.2, 9.8, 19.5, 21.5]:
    put(h, tone(N(83), 0.07, 0.15))
    put(h + 0.07, tone(N(88), 0.35, 0.13))
for c in np.arange(19.55, 20.3, 0.1):
    put(c, tone(N(90), 0.06, 0.07))
for c in np.arange(21.55, 22.3, 0.1):
    put(c, tone(N(91), 0.06, 0.07))
for k in range(8):  # pipe down
    put(14.0 + k * 0.1, tone(N(60 - k * 2), 0.09, 0.14))
for k in range(12):  # sparkle / morph
    put(16.2 + k * 0.06, tone(N(84 + (k % 4) * 3), 0.05, 0.07))
sweep(25.55, 1200, 250, 0.9, 0.12)  # flag slide
for k, n in enumerate([67, 72, 76, 79, 84, 88, 84, 88, 91]):  # fanfare
    put(26.6 + k * 0.16, tone(N(n), 0.15 if k < 8 else 0.9, 0.14))
    put(26.6 + k * 0.16, tone(N(n - 12), 0.15 if k < 8 else 0.9, 0.08, kind="tri"))
for f in [27.0, 27.6, 28.2, 28.8]:
    put(f, tone(0, 0.5, 0.25, kind="noise") * np.exp(-np.linspace(0, 6, int(SR * 0.5))))
music(27.9, 30.0, transpose=5)
out[-int(SR * 0.5):] *= np.linspace(1, 0, int(SR * 0.5))
out = np.clip(out / max(1e-9, np.abs(out).max()) * 0.9, -1, 1)
with wave.open("audio.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((out * 32767).astype(np.int16).tobytes())
