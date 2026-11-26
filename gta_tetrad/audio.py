# Synthesised score + SFX for "GTA: Notebook" (30.0 s, 48 kHz stereo). Usage: python3 audio.py out.wav
import numpy as np, wave, sys
SR = 48000; D = 30.0; n = int(SR * D)
t = np.arange(n) / SR
rng = np.random.default_rng(7)
L = np.zeros(n); Rr = np.zeros(n); mus = np.zeros(n)

def tt(d): return np.arange(int(d * SR)) / SR
def put(buf, sig, at, g=1.0):
    i = int(at * SR); j = min(n, i + len(sig))
    if j > i and i >= 0: buf[i:j] += sig[: j - i] * g
def add(sig, at, g=1.0, pan=0.0):
    put(L, sig, at, g * np.sqrt(0.5 * (1 - pan))); put(Rr, sig, at, g * np.sqrt(0.5 * (1 + pan)))
def madd(sig, at, g=1.0): put(mus, sig, at, g)
def lp(x, fc):
    fc = np.broadcast_to(np.asarray(fc, float), x.shape)
    a = 1 - np.exp(-2 * np.pi * fc / SR); y = np.empty_like(x); z = 0.0
    for i in range(len(x)): z += a[i] * (x[i] - z); y[i] = z
    return y
def hp(x, fc): return x - lp(x, fc)
def noise(d): return rng.standard_normal(len(tt(d)))
def bpn(d, lo, hi): return hp(lp(noise(d), hi), lo)
def ph(f, x): return np.cumsum(np.broadcast_to(f, x.shape)) / SR
def sine(f, x): return np.sin(2 * np.pi * ph(f, x))
def saw(f, x): return 2 * (ph(f, x) % 1) - 1
def sq(f, x, duty=0.5): return np.where(ph(f, x) % 1 < duty, 1.0, -1.0)
def gate(x, d, a=0.005, r=0.01): return np.minimum(1, x / a) * np.minimum(1, np.maximum(0, d - x) / r)

NT = {'G1': 49.0, 'A1': 55.0, 'C2': 65.41, 'D2': 73.42, 'E2': 82.41, 'F2': 87.31, 'G2': 98.0, 'A2': 110.0, 'C3': 130.8, 'D3': 146.8,
      'E3': 164.8, 'G3': 196.0, 'A3': 220.0, 'B3': 246.9, 'C4': 261.6, 'D4': 293.7, 'E4': 329.6, 'G4': 392.0, 'A4': 440.0,
      'B4': 493.9, 'C5': 523.3, 'D5': 587.3, 'E5': 659.3, 'G5': 784.0, 'A5': 880.0}
B = 0.5
# ---------- instruments ----------
def kick():
    x = tt(0.35); return sine(45 + 110 * np.exp(-x * 30), x) * np.exp(-x * 9) + 0.3 * bpn(0.35, 1000, 4000) * np.exp(-x * 120)
def snare():
    x = tt(0.25); return 0.6 * bpn(0.25, 1200, 7000) * np.exp(-x * 18) + 0.4 * sine(190, x) * np.exp(-x * 25)
def hat(op=False):
    d = 0.16 if op else 0.05; x = tt(d); return hp(noise(d), 7000) * np.exp(-x * (18 if op else 80))
def bass(f, d):
    x = tt(d); s = lp(saw(f, x) * 0.6 + sine(f, x), 600 + 900 * np.exp(-x * 12)); return s * np.exp(-x * 3) * gate(x, d)
def pluck(f, d=0.25):
    x = tt(d); return lp(saw(f, x), 1800 * np.exp(-x * 10) + 200) * np.exp(-x * 14) * gate(x, d, 0.002)
def lead(f0, f1, d):
    x = tt(d); f = f0 + (f1 - f0) * np.minimum(1, x / 0.06); v = 1 + 0.012 * np.sin(2 * np.pi * 6 * x) * np.minimum(1, x / 0.15)
    return lp(sine(f * v, x) * 0.7 + 0.3 * sq(f * v, x, 0.3), 3000) * gate(x, d, 0.01, 0.04)
def whistle(f, d):
    x = tt(d); v = 1 + 0.01 * np.sin(2 * np.pi * 5.5 * x); return (sine(f * v, x) + 0.05 * bpn(d, 2000, 6000)) * gate(x, d, 0.02, 0.03)
def stab(freqs, d=0.6):
    x = tt(d); s = sum(saw(f, x) + saw(f * 1.006, x) for f in freqs) / len(freqs)
    return lp(s, 400 + 5000 * np.exp(-x * 6)) * np.exp(-x * 3.5) * gate(x, d, 0.003, 0.05)
def boom(d=1.0):
    x = tt(d); return sine(38 + 60 * np.exp(-x * 12), x) * np.exp(-x * 4) + 0.5 * bpn(d, 60, 800) * np.exp(-x * 9)
def crash():
    x = tt(1.4); return hp(noise(1.4), 4000) * np.exp(-x * 3.2) * 0.5
KICK, SNR = kick(), snare()

# ---------- arrangement ----------
def groove(t0, t1, kicks=True, snares=True, hat16=False, hatg=1.0):
    for k, bt in enumerate(np.arange(t0, t1 - 1e-6, B / 2)):
        pos = k % 8
        if kicks and (pos in (0, 5) or (pos == 3 and (k // 8) % 2)): madd(KICK, bt, 0.9)
        if snares and pos in (2, 6): madd(SNR, bt, 0.55)
        madd(hat(pos == 7), bt + (0.03 if pos % 2 else 0), hatg * (0.16 if pos % 2 else 0.22))
        if hat16: madd(hat(), bt + B / 4, 0.09 * hatg)
BL = ['A1', 'A1', 'C2', 'D2', 'A1', 'A1', 'E2', 'G1']
def bassline(t0, t1, octave_hits=True, g=0.55):
    for k, bt in enumerate(np.arange(t0, t1 - 1e-6, B)):
        nm = BL[k % 8]; madd(bass(NT[nm], B * (0.9 if k % 2 == 0 else 0.45)), bt, g)
        if octave_hits and k % 2 == 0: madd(bass(NT[nm] * 2, B * 0.25), bt + B * 0.75, 0.25)
MOT = [(0.0, 'E4', 'E4', 0.45), (0.5, 'C4', 'C4', 0.2), (0.75, 'D3', 'E4', 0.5), (1.5, 'A3', 'C4', 0.4)]
MOT2 = [(0.0, 'A4', 'A4', 0.3), (0.5, 'G4', 'A4', 0.4), (1.0, 'E4', 'E4', 0.25), (1.25, 'D4', 'E4', 0.6)]
def motif(at, m, g=0.18):
    for off, a, b, d in m: madd(lead(NT[a], NT[b], d), at + off, g)

# intro 0-3: whistling stickman, sneaky pizzicato, riser into the heist
for i, (nm, d) in enumerate([('E5', 0.14), ('G5', 0.14), ('A5', 0.22), ('G5', 0.12), ('E5', 0.24)]):
    add(whistle(NT[nm], d), 0.15 + sum(x[1] for x in [('E5', 0.14), ('G5', 0.14), ('A5', 0.22), ('G5', 0.12), ('E5', 0.24)][:i]) + 0.02 * i, 0.16, -0.3)
for k in range(10): madd(hat(), 0.95 + k * 0.25, 0.08)   # clock tick
for k, nm in enumerate(['A2', 'C3', 'E3', 'G3', 'A2', 'C3', 'E3', 'G3']): madd(pluck(NT[nm]), 1.9 + k * 0.1, 0.3)  # tiptoe (one note per step)
for k, nm in enumerate(['A2', 'E3', 'A3', 'C4']): madd(pluck(NT[nm], 0.35), 1.0 + k * 0.25, 0.22)
x = tt(0.7); madd(lp(noise(0.7), 300 + 6000 * (x / 0.7) ** 3) * (x / 0.7) ** 3 * 0.35, 2.3)
# A section 3.0-8.55
groove(3.0, 8.55); bassline(3.0, 8.55); motif(3.0, MOT); motif(5.0, MOT); motif(7.0, MOT2, 0.16)
madd(crash(), 3.0, 0.5)
# record scratch + "teacher at work" breakdown
x = tt(0.35); madd(lp(saw(900 * np.exp(-x * 7) + 120 * np.sin(2 * np.pi * 9 * x), x), 3000) * np.exp(-x * 4) * 0.5, 8.55)
for k, bt in enumerate(np.arange(9.0, 10.5, B)): madd(pluck(NT[['A2', 'G2', 'F2', 'E2'][k % 4]], 0.18), bt, 0.5)
for k, bt in enumerate(np.arange(9.0, 10.5, B / 2)): madd(hat(), bt, 0.12)
for k in range(12): r = 9.9 + k * (0.6 / 12); madd(SNR, r, 0.12 + 0.03 * k)  # snare roll build
# B section 10.5-15.75 (more drive) with strike hits on the beat
groove(10.5, 15.75, hat16=True); bassline(10.5, 15.75); motif(10.5, MOT2); motif(12.5, MOT); motif(14.5, MOT2, 0.15)
madd(crash(), 10.5, 0.55)
for s in (12.5, 13.5, 14.5): madd(stab([NT['A3'], NT['C4'], NT['E4']], 0.5), s, 0.32); madd(boom(0.6), s, 0.45)
for k in range(6): madd(SNR, 15.75 + k * 0.042, 0.2 + 0.05 * k)                # fill into the jump
groove(16.0, 18.0); bassline(16.0, 18.0); motif(16.0, MOT, 0.16)
madd(crash(), 17.0, 0.65)
# stealth 18-21.6
groove(18.0, 21.6, kicks=False, snares=False, hatg=0.8)
for k, bt in enumerate(np.arange(18.0, 21.6, B)): madd(bass(NT[['A1', 'A1', 'G1', 'A1'][k % 4]], 0.3), bt, 0.5)
for k, bt in enumerate(np.arange(18.0, 21.6, 1.0)): madd(pluck(NT['E4'] if k % 2 else NT['D4'], 0.3), bt + 0.75, 0.18)
madd(stab([NT['A3'], NT['D4'] * 1.06, NT['E4'] * 1.06], 0.9), 20.6, 0.35)   # "spotted!" sting
# wind-up 21.6-23.45: riser + accelerating snare, cut at the fold
x = tt(1.9); madd(lp(saw(55 + 400 * (x / 1.9) ** 2, x) + 0.6 * noise(1.9), 200 + 5000 * (x / 1.9) ** 2) * (x / 1.9) ** 1.5 * 0.35, 21.6)
r = 21.6
while r < 23.4: madd(SNR, r, 0.1 + 0.25 * (r - 21.6) / 1.8); r += 0.25 - 0.2 * (r - 21.6) / 1.8
for bt in np.arange(21.6, 23.4, B): madd(KICK, bt, 0.6)
# slow-mo filter during the jump, then hard cut by the page fold
fc = np.full(n, 16000.0); j = (t > 16.0) & (t < 17.0); fc[j] = 16000 - 15200 * np.sin(np.pi * (t[j] - 16.0)) ** 0.6
mus = lp(mus, fc)
cut = int(23.45 * SR); f = int(0.012 * SR); mus[cut - f:cut] *= np.linspace(1, 0, f); mus[cut:] = 0
x = tt(0.18); madd(saw(220 * np.exp(-x * 9), x) * np.exp(-x * 10) * 0.25, 23.43)
# epilogue music: soft chime on the caption, pluck on the logo, closing chord
x = tt(1.6)
for fq, g in ((NT['C5'], 0.5), (NT['E5'], 0.35), (NT['G5'], 0.3), (NT['C4'], 0.4)): madd(sine(fq, x) * np.exp(-x * 2.2) * gate(x, 1.6, 0.004, 0.2), T_cap := 25.5, g * 0.4)
madd(pluck(NT['C4'], 0.6), 26.4, 0.3); madd(pluck(NT['G4'], 0.6), 26.55, 0.25)
x = tt(1.4)
for fq in (NT['A3'], NT['C4'], NT['E4'], NT['A4']): madd(sine(fq, x) * np.minimum(1, x / 0.05) * np.exp(-x * 1.5), 28.6, 0.12)
L += mus * 0.9; Rr += mus * 0.9

# ---------- SFX ----------
def thock(f=180): x = tt(0.12); return sine(f * (1 + 0.6 * np.exp(-x * 60)), x) * np.exp(-x * 40) + 0.4 * bpn(0.12, 800, 3000) * np.exp(-x * 80)
def scribble(d, rate=11, lo=1500, hi=6000):
    x = tt(d); am = 0.5 + 0.5 * np.abs(np.sin(np.pi * rate * x + 0.3 * np.sin(2 * np.pi * 3 * x))); return bpn(d, lo, hi) * am * gate(x, d, 0.01, 0.02)
def boing(f0, f1, d): x = tt(d); return sine(f0 + (f1 - f0) * x / d, x) * np.exp(-x * 6)
for i, ch in enumerate("GTA: NOTEBOOK"):
    if ch != ' ': add(thock(150 + 10 * i), 0.08 + i * 0.055 + 0.17, 0.5, -0.4 + i * 0.065)
add(scribble(0.35, 9), 0.9, 0.22, 0.2)
x = tt(0.18); add(sine(1200 + 600 * x / 0.18, x) * np.exp(-x * 12), 0.95, 0.22)       # "!"
add(scribble(0.4, 8, 1200, 4000), 1.15, 0.12, -0.4)                                  # speech bubble pop-in
add(boing(300, 800, 0.22), 2.3, 0.35); add(thock(90), 2.55, 0.8)                       # hop + seat
# engine
x = tt(17.6 - 2.55); te = x + 2.55
ke = [2.55, 2.7, 2.85, 3.0, 3.2, 3.6, 8.5, 11.5, 15.9, 16.0, 17.0, 17.1, 17.45, 17.55]
fe = np.interp(te, ke, [40, 95, 60, 110, 70, 75, 80, 82, 105, 125, 110, 60, 50, 40])
ge = np.interp(te, ke, [0, 0.6, 0.4, 0.7, 0.5, 0.35, 0.35, 0.35, 0.5, 0.25, 0.15, 0.5, 0.3, 0.0])
add(lp(saw(fe, x) + 0.6 * sq(fe * 0.5, x, 0.3), 900) * ge, 2.55, 0.45)
# siren, tied to the cap light
x = tt(23.1 - 3.6); p2 = np.floor(x / 0.32) % 2; fs = np.where(p2 == 0, 960, 720)
add(lp(sine(fs * (1 + 0.004 * np.sin(2 * np.pi * 7 * x)), x) * 0.5 + 0.2 * sq(fs, x), 2500) * gate(x, len(x) / SR, 0.3, 0.05), 3.6, 0.065, 0.3)
add(scribble(8.55 - 3.65, 14, 2500, 8000), 3.65, 0.06, -0.3)                           # pen line
add(scribble(15.9 - 10.3, 14, 2500, 8000), 10.3, 0.06, -0.3)
for p in (5.0, 6.0, 11.0):                                                            # wanted stars
    add(scribble(0.24, 18, 2000, 7000), p - 0.24, 0.3, 0.6)
    x = tt(0.6); add((sine(1320, x) + 0.5 * sine(1980, x)) * np.exp(-x * 7), p, 0.18 if p < 11 else 0.26, 0.6)
# teacher's reflex: screech, two slashes, writing "4", tick
x = tt(0.3); add(lp(saw(1800 - 1200 * x / 0.3, x), 4000) * np.exp(-x * 6) * 0.4 + bpn(0.3, 2000, 6000) * 0.3, 8.55, 0.35, -0.2)
for a, d in ((8.8, 0.15), (9.08, 0.14), (9.4, 0.22), (9.75, 0.13), (10.0, 0.18)): add(scribble(d, 22, 2000, 7000), a, 0.45, -0.1)
x = tt(0.4); add((sine(1046, x) + sine(1568, x)) * np.exp(-x * 9), 10.18, 0.2)          # "correct!" ding
x = tt(0.35); add(sine(260 + 60 * np.sin(2 * np.pi * 14 * x), x) * np.exp(-x * 5), 10.85, 0.18, 0.3)  # "ha-ha" wobble
# strikes: whoosh in, stab-thud, car tyre squeal
for s, dd in zip((12.5, 13.5, 14.5), (-1, 1, -1)):
    x = tt(0.45); add(bpn(0.45, 400, 4000) * np.sin(np.pi * x / 0.45) ** 2, s - 0.45, 0.45, 0.2)
    add(thock(70), s, 0.9); add(scribble(0.14, 30, 1500, 5000), s, 0.35)
    x = tt(0.35); add(lp(sq(1400 + 200 * np.sin(2 * np.pi * 30 * x), x, 0.4), 3000) * np.exp(-x * 7) * 0.25, s - 0.2, 0.3, 0.6 * dd)
add(scribble(0.3, 10, 1200, 4000), 14.95, 0.1)                                         # "Hold on!" bubble
x = tt(0.9); add(bpn(0.9, 300, 3000) * np.sin(np.pi * x / 0.9) ** 2, 15.8, 0.35)          # jump whoosh
x = tt(0.5); add(sine(50 * np.exp(-x * 4) + 30, x) * np.exp(-x * 7) + 0.6 * bpn(0.5, 100, 1500) * np.exp(-x * 12), 17.0, 0.9)
add(scribble(0.45, 30, 1500, 5000) * np.linspace(1, 0.2, len(tt(0.45))), 17.05, 0.3)
add(thock(260), 17.55, 0.4)
for k in range(4): add(thock(420 + 30 * k) * 0.6, 17.72 + k * 0.08, 0.35, 0.2)
x = tt(0.35); add(sine(500 * np.exp(-x * 9) + 90, x) * np.exp(-x * 9) + 0.3 * bpn(0.35, 200, 1200) * np.exp(-x * 14), 18.0, 0.55)
for k, s in enumerate(np.arange(18.85, 20.5, 0.3)): x = tt(0.12); add(bpn(0.12, 2500, 6000) * np.sin(np.pi * x / 0.12), s, 0.18, -0.3 + 0.12 * k)
x = tt(0.08); add(sine(1800, x) * np.exp(-x * 40), 19.65, 0.2, 0.3)                     # eyes
x = tt(0.1); add(sine(900, x) * np.exp(-x * 30), 20.64, 0.25, 0.3)                      # eyes duck
x = tt(0.08); add(sine(2100, x) * np.exp(-x * 40), 22.25, 0.2, 0.3)                     # eyes again
x = tt(1.25); add(bpn(1.25, 500, 6000) * np.sin(np.pi * np.clip(x / 1.05, 0, 1)) ** 1.5 * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 9 * x))), 22.98, 0.7, 0.2)
x = tt(0.3); add(bpn(0.3, 80, 900) * np.exp(-x * 14), 24.08, 0.6)
add(scribble(0.5, 12, 2000, 7000), T_q := 24.7, 0.3, 0.3)
add(scribble(0.6, 10, 1500, 6000), 25.5, 0.16, -0.2)
x = tt(0.5); add(bpn(0.5, 600, 5000) * np.sin(np.pi * x / 0.5), 26.95, 0.35, 0.6)          # corner peel
def horn(at): x = tt(0.14); add(lp(sq(420, x, 0.45) + sq(530, x, 0.45), 2500) * gate(x, 0.14, 0.005, 0.02) * 0.4, at, 0.4, 0.6)
horn(27.45); horn(27.65)
for i, (nm, d) in enumerate([('A5', 0.14), ('G5', 0.14), ('E5', 0.3)]): add(whistle(NT[nm], d), 27.95 + i * 0.17, 0.14, 0.6)
x = tt(0.25); add(bpn(0.25, 80, 1200) * np.exp(-x * 16), 28.55, 0.5)                     # page snaps back

# ---------- master ----------
st = np.stack([L, Rr], 1)
st = np.tanh(st * 1.1) / np.tanh(1.1)
f = int(0.3 * SR); st[-f:] *= np.linspace(1, 0, f)[:, None]
st *= 0.891 / np.max(np.abs(st))
with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype('<i2').tobytes())
print('ok', st.shape)
