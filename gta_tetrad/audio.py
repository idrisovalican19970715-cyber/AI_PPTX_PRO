# Synthesised score + SFX for "GTA: Тетрадь" (10.0 s, 48 kHz stereo)
import numpy as np, wave, sys
SR = 48000; D = 10.0; n = int(SR * D)
t = np.arange(n) / SR
rng = np.random.default_rng(7)
L = np.zeros(n); Rr = np.zeros(n)

def add(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR); j = min(n, i + len(sig))
    if j <= i: return
    s = sig[: j - i] * gain
    L[i:j] += s * np.sqrt(0.5 * (1 - pan)); Rr[i:j] += s * np.sqrt(0.5 * (1 + pan))

def tt(d): return np.arange(int(d * SR)) / SR
def lp(x, fc):
    fc = np.broadcast_to(np.asarray(fc, float), x.shape)
    a = 1 - np.exp(-2 * np.pi * fc / SR); y = np.empty_like(x); z = 0.0
    for i in range(len(x)): z += a[i] * (x[i] - z); y[i] = z
    return y
def hp(x, fc): return x - lp(x, fc)
def bp_noise(d, fc_lo, fc_hi): return hp(lp(rng.standard_normal(len(tt(d))), fc_hi), fc_lo)
def env(d, a=0.005, r=0.1, curve=1.0):
    x = tt(d); e = np.minimum(1, x / max(a, 1e-4)) * np.exp(-np.maximum(0, x - a) / r * curve); return e
def saw(f, x): ph = np.cumsum(np.broadcast_to(f, x.shape)) / SR; return 2 * (ph % 1) - 1
def sq(f, x, duty=0.5): ph = np.cumsum(np.broadcast_to(f, x.shape)) / SR; return np.where(ph % 1 < duty, 1.0, -1.0)
def sine(f, x): ph = np.cumsum(np.broadcast_to(f, x.shape)) / SR; return np.sin(2 * np.pi * ph)

BPM = 120; B = 60 / BPM; M0 = 1.5  # music downbeat
# ---------------- MUSIC (bus) ----------------
mus = np.zeros(n)
def madd(sig, at, g=1.0):
    i = int(at * SR); j = min(n, i + len(sig))
    if j > i: mus[i:j] += sig[: j - i] * g
def kick(g=1.0):
    x = tt(0.35); f = 45 + 110 * np.exp(-x * 30); return sine(f, x) * np.exp(-x * 9) * g + 0.3 * bp_noise(0.35, 1000, 4000) * np.exp(-x * 120)
def snare():
    x = tt(0.25); return 0.6 * bp_noise(0.25, 1200, 7000) * np.exp(-x * 18) + 0.4 * sine(190, x) * np.exp(-x * 25)
def hat(open_=False):
    d = 0.16 if open_ else 0.05; x = tt(d); return hp(rng.standard_normal(len(x)), 7000) * np.exp(-x * (18 if open_ else 80))
KICK, SNR = kick(), snare()
notes = {'A1': 55.0, 'C2': 65.41, 'D2': 73.42, 'E2': 82.41, 'G1': 49.0, 'A2': 110.0, 'C3': 130.8, 'D3': 146.8, 'E3': 164.8, 'G3': 196.0, 'A3': 220.0, 'C4': 261.6, 'E4': 329.6}
def bass(fr, d):
    x = tt(d); s = saw(fr, x) * 0.6 + sine(fr, x); s = lp(s, 600 + 900 * np.exp(-x * 12)); return s * np.minimum(1, x / 0.005) * np.exp(-x * 3) * np.minimum(1, (d - x) / 0.01)
def lead(f0, f1, d):  # gliding G-funk whistle lead
    x = tt(d); f = f0 + (f1 - f0) * np.minimum(1, x / 0.06); vib = 1 + 0.012 * np.sin(2 * np.pi * 6 * x) * np.minimum(1, x / 0.15)
    s = sine(f * vib, x) * 0.7 + 0.3 * sq(f * vib, x, 0.3); s = lp(s, 3000); return s * np.minimum(1, x / 0.01) * np.minimum(1, (d - x) / 0.04)

end_music = 8.22  # cut by the page fold
search0, search1 = 6.5, 7.75
beats = np.arange(M0, end_music, B / 2)  # 8th grid
for k, bt in enumerate(beats):
    pos = k % 8  # 8 eighths per bar
    searching = search0 <= bt < search1
    jumping = 4.5 <= bt < 5.5
    if not searching:
        if pos in (0, 5) or (pos == 3 and k // 8 % 2): madd(KICK, bt, 0.9)
        if pos in (2, 6): madd(SNR, bt, 0.55)
    madd(hat(pos == 7), bt + (0.03 if pos % 2 else 0), 0.16 if pos % 2 else 0.22)
    if searching and pos in (0, 4): madd(KICK, bt, 0.35)
# bass line (per beat)
bl = ['A1', 'A1', 'C2', 'D2', 'A1', 'A1', 'E2', 'G1']
for k, bt in enumerate(np.arange(M0, end_music, B)):
    nm = bl[k % 8]; d = B * (0.9 if k % 2 == 0 else 0.45)
    madd(bass(notes[nm], d), bt, 0.55)
    if k % 2 == 0 and not (search0 <= bt < search1): madd(bass(notes[nm] * 2, B * 0.25), bt + B * 0.75, 0.25)
# lead motif (siren-like) bars 1,2 ; answer in bar 3
mot = [(0.0, 'E4', 'E4', 0.45), (0.5, 'C4', 'C4', 0.2), (0.75, 'D3', 'E4', 0.5), (1.5, 'A3', 'C4', 0.4)]
for bar0 in (M0, M0 + 4 * B):
    for off, a, b, d in mot: madd(lead(notes[a], notes[b], d), bar0 + off * 1, 0.18)
for off, a, b, d in [(0.0, 'A3', 'A3', 0.3), (0.5, 'G3', 'A3', 0.6)]: madd(lead(notes[a], notes[b], d), 5.5 + off, 0.16)
# intro riser 0-1.5 (filtered noise + low pad)
x = tt(1.5); pad = (sine(55, x) + 0.5 * sine(110.5, x) + 0.3 * saw(82.4, x)) * (x / 1.5) ** 2 * 0.35
madd(pad + lp(rng.standard_normal(len(x)), 300 + 3000 * (x / 1.5) ** 3) * (x / 1.5) ** 3 * 0.25, 0.0)
# crash on landing + on go
def crash(): x = tt(1.2); return hp(rng.standard_normal(len(x)), 4000) * np.exp(-x * 3.5) * 0.5
madd(crash(), M0, 0.5); madd(crash(), 5.5, 0.6)
# slow-mo filter during the jump + hard cut at the page fold
fc = np.full(n, 16000.0)
j = (t > 4.5) & (t < 5.5); u = (t[j] - 4.5)
fc[j] = 16000 - 15200 * np.sin(np.pi * u) ** 0.6
mus = lp(mus, fc)
cut = int(end_music * SR); fade = int(0.012 * SR)
mus[cut - fade:cut] *= np.linspace(1, 0, fade); mus[cut:] = 0
# tape-stop flavour just before the cut (short pitch-dive blip)
x = tt(0.18); madd(saw(220 * np.exp(-x * 9), x) * np.exp(-x * 10) * 0.25, end_music - 0.02)
L += mus * 0.9; Rr += mus * 0.9

# ---------------- SFX ----------------
def thock(f=180): x = tt(0.12); return (sine(f * (1 + 0.6 * np.exp(-x * 60)), x) * np.exp(-x * 40) + 0.4 * bp_noise(0.12, 800, 3000) * np.exp(-x * 80))
title = "GTA: ТЕТРАДЬ"
for i, ch in enumerate(title):
    if ch != ' ': add(thock(150 + 12 * i), 0.08 + i * 0.055 + 0.17, 0.55, -0.4 + i * 0.07)
def scribble(d, rate=11, lo=1500, hi=6000):
    x = tt(d); s = bp_noise(d, lo, hi); am = 0.5 + 0.5 * np.abs(np.sin(np.pi * rate * x + 0.3 * np.sin(2 * np.pi * 3 * x)))
    return s * am * np.minimum(1, x / 0.01) * np.minimum(1, (d - x) / 0.02)
add(scribble(0.35, 9), 0.75, 0.25, 0.2)                     # red underline
x = tt(0.22); add(sine(300 + 500 * x / 0.22, x) * np.exp(-x * 6) * 0.5, 1.05, 0.35)  # hop "boing"
add(thock(90), 1.27, 0.8)                                    # lands in seat
# engine: rev 1.3-1.5, drive, ramp rise, stop
x = tt(6.0 - 1.3); te = x + 1.3
def interp(k): return np.interp(te, [1.3, 1.45, 1.6, 2.2, 4.0, 4.45, 4.5, 5.5, 5.6, 5.95, 6.0], k)
fe = interp([45, 85, 60, 70, 82, 100, 120, 110, 60, 50, 40])
ge = interp([0.0, 0.6, 0.5, 0.35, 0.35, 0.5, 0.25, 0.15, 0.5, 0.3, 0.0])
eng = lp(saw(fe, x) + 0.6 * sq(fe * 0.5, x, 0.3), 900) * ge
add(eng, 1.3, 0.45)
# siren (pen police): two-tone, tied to the cap light, quiet under the music
x = tt(7.85 - 2.0); ph = np.floor((x + 0.0) / 0.32) % 2
sir = sine(np.where(ph == 0, 960, 720) * (1 + 0.004 * np.sin(2 * np.pi * 7 * x)), x) * 0.5 + 0.2 * sq(np.where(ph == 0, 960, 720), x)
sir = lp(sir, 2500) * np.minimum(1, x / 0.3) * np.minimum(1, (len(x) / SR - x) / 0.05)
add(sir, 2.0, 0.07, 0.3)
add(scribble(6.75 - 2.05, 14, 2500, 8000), 2.05, 0.06, -0.3)   # pen ink line
for s in (2.36, 2.86, 3.36):                                     # stars: scribble + ding on the beat
    add(scribble(0.24, 18, 2000, 7000), s - 0.1, 0.3, 0.6)
    x = tt(0.6); add((sine(1320, x) + 0.5 * sine(1980, x)) * np.exp(-x * 7) * 0.5, s + 0.14, 0.35, 0.6)
x = tt(0.9); add(bp_noise(0.9, 300, 3000) * np.sin(np.pi * x / 0.9) ** 2, 4.3, 0.35)  # jump whoosh
x = tt(0.5); add(sine(50 * np.exp(-x * 4) + 30, x) * np.exp(-x * 7) + 0.6 * bp_noise(0.5, 100, 1500) * np.exp(-x * 12), 5.5, 0.9)  # landing
add(scribble(0.45, 30, 1500, 5000) * np.linspace(1, 0.2, len(tt(0.45))), 5.55, 0.3)  # graphite skid
add(thock(260), 6.05, 0.4)
for k in range(4): add(thock(420 + 30 * k) * 0.6, 6.22 + k * 0.08, 0.35, 0.2)  # tiny footsteps
x = tt(0.35); add(sine(500 * np.exp(-x * 9) + 90, x) * np.exp(-x * 9) + 0.3 * bp_noise(0.35, 200, 1200) * np.exp(-x * 14), 6.5, 0.55)  # dive into ink "bloop"
for k, s in enumerate(np.arange(6.85, 7.7, 0.3)):                 # sniff
    x = tt(0.12); add(bp_noise(0.12, 2500, 6000) * np.sin(np.pi * x / 0.12), s, 0.18, -0.3 + 0.2 * k)
x = tt(0.08); add(sine(1800, x) * np.exp(-x * 40), 7.05, 0.2, 0.3)  # eyes peek blip
x = tt(1.25); pt = bp_noise(1.25, 500, 6000) * (np.sin(np.pi * np.clip(x / 1.05, 0, 1)) ** 1.5) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 9 * x)))
add(pt, 7.78, 0.7, 0.2)                                           # page turn rustle
x = tt(0.3); add(bp_noise(0.3, 80, 900) * np.exp(-x * 14), 8.83, 0.6)  # page settles
add(scribble(0.45, 12, 2000, 7000), 9.0, 0.3, 0.3)               # "?" written
x = tt(0.85)
for f, g in ((1046.5, 0.5), (1318.5, 0.35), (1568, 0.3), (523.25, 0.4)):
    add(sine(f, x) * np.exp(-x * 3.2) * np.minimum(1, x / 0.004), 9.15, g * 0.4)   # soft "case closed" chime
x = tt(0.4); add(scribble(0.4, 10, 1500, 6000), 9.15, 0.18, -0.2)  # caption writing

# ---------------- master ----------------
st = np.stack([L, Rr], 1)
# gentle saturation + normalise to -1 dBFS peak, fade the last 60 ms
st = np.tanh(st * 1.1) / np.tanh(1.1)
f = int(0.06 * SR); st[-f:] *= np.linspace(1, 0, f)[:, None]; st[:int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))[:, None]
st *= 0.891 / np.max(np.abs(st))
with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype('<i2').tobytes())
print('ok', st.shape, 'rms', float(np.sqrt((st ** 2).mean())))
