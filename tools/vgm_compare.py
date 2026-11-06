#!/usr/bin/env python3
"""Compare a Top Gear 2 VGM rip with the native port's own chip-write stream.

Two things are measured, both from YM2612 register traffic only (no audio, no
envelopes, so loop aliasing cannot fool them):

  tempo   the music clock is the YM2612 timer B overflow the driver polls at
          Z80 $0BFC. Its tick is the `$27` write that reloads the timer, so a
          per-channel key-on train plus the tick train give the tempo directly:
            * global ratio (port / reference) from the mean tick interval,
            * global ratio from a linear regression of matched key-on times,
            * global ratio from the loop period (when both sides cover a loop),
            * local ratio in 1 s windows (sliding regression) and its spread.

  logic   the ordered sequence of musical events with timing ignored: key-on /
          key-off per channel, the 11-bit block+fnum per channel, the
          algorithm/feedback and stereo registers, every operator parameter
          ($30-$9F) and the DAC channel ($2A/$2B). A wrong note, a wrong patch
          or a missing channel shows up as a divergence even when the tempo is
          right.

Inputs
  --vgm FILE     a VGM v1.5 rip (the owner's rips, or one the port logged)
  --dump FILE    a GENESIS_AUDIO_WRITEDUMP stream from the port
                 (`f=<frame> sl=<line> FM p0 $xx mc=<master> wf=.. pcz=$..`)
  --ticklog FILE optional GENESIS_YM_TICKLOG stream, to report how many Z80
                 cycles the guest actually got per tick (starvation check)

  python3 tools/vgm_compare.py --vgm ref.vgm --dump writes.txt
  python3 tools/vgm_compare.py --selftest

Timestamps. The VGM clock is 44100 Hz samples. The port's dump carries the
sound frame and the master-cycle offset inside it, so its absolute time is
`(frame * 262 * 3420 + mc) / 53693175` seconds: exact guest time, not host time.
Both are compared in seconds; the reference sample grid only quantises the VGM
side (1/44100 s = 22.7 us).

Nothing here writes outside the paths given on the command line. The rips are
game-derived and never go into git; only the numbers do.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import struct
import sys

# --- machine constants -----------------------------------------------------
VGM_RATE = 44100.0
MASTER_CLOCK = 53693175          # NTSC 68k clock = 7 * 7670453 (YM2612 clock)
MASTER_PER_FRAME = 262 * 3420    # one NTSC frame in master cycles
YM_TIMER_B_MASTER_TICK = 16 * 144 * 7   # master cycles per timer-B unit

# YM2612 $27 mode bits
T27_LOAD_B = 0x02

# register classes for the logic comparison
CLASS_ORDER = ['keyon', 'keyoff', 'freq', 'alg', 'stereo', 'op', 'dac', 'dacen', 'other']


# --------------------------------------------------------------- input side
class Stream:
    """A timestamped raw chip-write stream plus its provenance."""

    def __init__(self, name, writes, meta=None):
        self.name = name
        self.writes = writes          # [(t_seconds, port, value)], port 4 = PSG
        self.meta = meta or {}

    # -- register view -----------------------------------------------------
    def regs(self):
        """[(t, bank, reg, value)] with the YM2612 address latch resolved."""
        out = []
        latch = [0, 0]
        for t, port, val in self.writes:
            if port == 4:
                continue
            bank = port >> 1
            if port & 1:
                out.append((t, bank, latch[bank], val))
            else:
                latch[bank] = val
        return out


def read_vgm(path):
    """Parse a VGM v1.5 file into a raw write stream."""
    d = open(path, 'rb').read()
    if d[:4] != b'Vgm ':
        raise SystemExit('%s: not a VGM file' % path)
    version = struct.unpack('<I', d[8:12])[0]
    data_off = struct.unpack('<I', d[0x34:0x38])[0] + 0x34
    ym_clock = struct.unpack('<I', d[0x2C:0x30])[0]
    total = struct.unpack('<I', d[0x18:0x1C])[0]
    loop_off = struct.unpack('<I', d[0x1C:0x20])[0]
    loop_n = struct.unpack('<I', d[0x20:0x24])[0]
    gd3_off = struct.unpack('<I', d[0x14:0x18])[0]

    writes = []
    i, samp, reserved = data_off, 0, collections.Counter()
    while i < len(d):
        c = d[i]
        if c == 0x52 or c == 0x53:                     # addr+data, port 0/1
            bank = c & 1
            writes.append((samp / VGM_RATE, bank * 2, d[i + 1]))
            writes.append((samp / VGM_RATE, bank * 2 + 1, d[i + 2]))
            i += 3
        elif c == 0x50 or c == 0x51:                   # data only, port 0/1
            writes.append((samp / VGM_RATE, (c & 1) * 2 + 1, d[i + 1]))
            i += 2
        elif c == 0x4F:                                # SN76489
            writes.append((samp / VGM_RATE, 4, d[i + 1]))
            i += 2
        elif c == 0x61:
            samp += struct.unpack('<H', d[i + 1:i + 3])[0]
            i += 3
        elif c == 0x62:
            samp += 735
            i += 1
        elif c == 0x63:
            samp += 882
            i += 1
        elif c == 0x66:                                # end of stream
            break
        elif c == 0x67:                                # data block
            size = struct.unpack('<I', d[i + 3:i + 7])[0]
            i += 7 + size
        elif 0x70 <= c <= 0x8F:                        # waits
            samp += (c & 0x0F) if c >= 0x80 else (c & 0x0F) + 1
            i += 1
        elif c == 0x68:                                # PCM RAM write
            i += 12
        elif 0x90 <= c <= 0x95:                        # DAC stream control
            i += {0x90: 5, 0x91: 3, 0x92: 3, 0x93: 11, 0x94: 2, 0x95: 2}[c]
        elif c == 0xE0:                                # seek PCM bank
            i += 2
        elif c < 0x40:                                 # reserved: 1-byte no-op
            reserved[c] += 1
            i += 1
        else:                                          # unknown: 1 byte, keep going
            reserved[c] += 1
            i += 1

    gd3 = {}
    if gd3_off and gd3_off + 12 <= len(d) and d[gd3_off:gd3_off + 4] == b'Gd3 ':
        size = struct.unpack('<I', d[gd3_off + 8:gd3_off + 12])[0]
        raw = d[gd3_off + 12:gd3_off + 12 + size].decode('utf-16-le', 'replace')
        parts = raw.split('\x00')
        fields = ['track', 'game', 'system', 'date', 'ripper', 'notes']
        gd3 = {k: (parts[n] if n < len(parts) else '') for n, k in enumerate(fields)}

    meta = dict(kind='vgm', path=str(path), version='%x.%02x' % (version >> 8, version & 0xFF),
                ym_clock=ym_clock, samples=total, seconds=total / VGM_RATE,
                loop_samples=loop_n, loop_seconds=loop_n / VGM_RATE,
                loop_offset=loop_off, gd3=gd3, reserved=dict(reserved))
    return Stream(path, writes, meta)


_WD_RE = None


def read_writedump(path):
    """Parse the engine's GENESIS_AUDIO_WRITEDUMP stream."""
    global _WD_RE
    if _WD_RE is None:
        import re
        _WD_RE = re.compile(r'^f=(\d+) sl=(\d+) (FM|PSG)\s+(?:p(\d) )?\$([0-9A-Fa-f]{2}) '
                            r'mc=(\d+) wf=\d+ pcz=\$([0-9A-Fa-f]{4})')
    writes = []
    frames = set()
    z80 = m68k = 0
    with open(path, 'r', errors='replace') as f:
        for line in f:
            m = _WD_RE.match(line)
            if not m:
                continue
            frame = int(m.group(1))
            mc = int(m.group(6))
            t = (frame * MASTER_PER_FRAME + mc) / MASTER_CLOCK
            if m.group(3) == 'PSG':
                writes.append((t, 4, int(m.group(5), 16)))
            else:
                writes.append((t, int(m.group(4)), int(m.group(5), 16)))
            frames.add(frame)
            if m.group(7).upper() == 'FFFF':
                m68k += 1
            else:
                z80 += 1
    meta = dict(kind='writedump', path=str(path), writes=len(writes),
                z80_writes=z80, m68k_writes=m68k,
                first_frame=min(frames) if frames else 0,
                last_frame=max(frames) if frames else 0,
                seconds=(max(writes, key=lambda w: w[0])[0] if writes else 0.0))
    return Stream(path, writes, meta)


# ------------------------------------------------------------ event extract
def timer_ticks(regs):
    """Times of the `$27` writes that load/run timer B (the music tick)."""
    return [t for t, bank, reg, val in regs
            if bank == 0 and reg == 0x27 and (val & T27_LOAD_B)]


def tick_stats(times):
    if len(times) < 3:
        return dict(count=len(times))
    iv = [b - a for a, b in zip(times, times[1:]) if 0 < b - a < 1.0]
    s = sorted(iv)
    return dict(count=len(iv), mean_ms=statistics.mean(iv) * 1e3,
                median_ms=statistics.median(iv) * 1e3,
                p05_ms=s[len(s) // 20] * 1e3, p95_ms=s[-len(s) // 20] * 1e3,
                min_ms=s[0] * 1e3, max_ms=s[-1] * 1e3,
                rate_hz=1.0 / statistics.mean(iv),
                span_s=times[-1] - times[0])


def key_events(regs):
    """[(t, channel, 'on'|'off', opmask)] from `$28`."""
    out = []
    for t, bank, reg, val in regs:
        if bank != 0 or reg != 0x28:
            continue
        ch = (val & 0x03) + (3 if val & 0x04 else 0)
        ops = (val >> 4) & 0x0F
        if ch > 5:
            continue
        out.append((t, ch, 'on' if ops else 'off', ops))
    return out


class _FreqState:
    """Latched $A0-$A6 pairs -> one event per real pitch change."""

    def __init__(self):
        self.hi = [0] * 6
        self.lo = [0] * 6
        self.seen = [None] * 6

    def feed(self, bank, reg, val):
        r = reg - 8 if bank else reg          # bank 1 uses $A8-$AE for ch 4-6
        if not (0xA0 <= r <= 0xA6) or (r & 0x03) == 3:
            return None
        ch = (r & 0x03) + (3 if bank else 0)
        if r & 0x04:
            self.hi[ch] = val & 0x3F
        else:
            self.lo[ch] = val
        cur = (self.hi[ch], self.lo[ch])
        if cur == self.seen[ch]:
            return None
        self.seen[ch] = cur
        return (ch, self.hi[ch] >> 3, ((self.hi[ch] & 7) << 8) | self.lo[ch])


def logic_tokens(regs, with_times=False):
    """Ordered musical events with no timing: (class, ...) tuples.

    One pass also returns each token's time (`with_times`), which the caller
    needs to cut a capture to the reference's musical span; the two used to be
    separate passes and doubled the peak memory on a 400k-write dump."""
    toks = []
    times = [] if with_times else None
    fs = _FreqState()
    for t, bank, reg, val in regs:
        tok = None
        if bank == 0 and reg == 0x28:
            ch = (val & 0x03) + (3 if val & 0x04 else 0)
            ops = (val >> 4) & 0x0F
            if ch <= 5:
                tok = ('keyon', ch, ops) if ops else ('keyoff', ch)
        elif (bank == 0 and 0xA0 <= reg <= 0xA6) or (bank == 1 and 0xA8 <= reg <= 0xAE):
            r = fs.feed(bank, reg, val)
            if r:
                tok = ('freq',) + r
        elif 0xB0 <= reg <= 0xB2:
            tok = ('alg', bank, reg & 3, val)
        elif 0xB4 <= reg <= 0xB6:
            tok = ('stereo', bank, reg & 3, val)
        elif 0x30 <= reg <= 0x9F:
            tok = ('op', bank, reg, val)
        elif bank == 0 and reg == 0x2A:
            tok = ('dac', val)
        elif bank == 0 and reg == 0x2B:
            tok = ('dacen', val)
        else:
            tok = ('other', bank, reg, val)
        if tok is not None:
            toks.append(tok)
            if with_times:
                times.append(t)
    return (toks, times) if with_times else toks


# --------------------------------------------------------------- comparison
def align_keyons(ref_keys, port_keys, probe=400):
    """Index in `port_keys` where the reference key-on/off train starts.

    Key events only: they are the musical skeleton, they exist in both streams,
    and they cannot be flooded by the port's DAC stream the way a full token
    list can. Returns (key_index, score 0..1)."""
    probe = min(probe, len(ref_keys), len(port_keys))
    if probe == 0:
        return 0, 0.0
    sig = lambda e: (e[1], e[2], e[3])          # channel, on/off, opmask
    ref_probe = [sig(e) for e in ref_keys[:probe]]
    best, best_score = 0, -1
    for off in range(0, max(1, len(port_keys) - probe)):
        score = 0
        for a, b in zip(ref_probe, port_keys[off:off + probe]):
            if a == sig(b):
                score += 1
        if score > best_score:
            best_score, best = score, off
            if score == probe:
                break
    return best, best_score / probe


def refine_offset(ref_tokens, port_tokens, off, span=8, window=4000):
    """Re-pick the start by matching the first `window` non-DAC tokens.

    The key-on train alone cannot resolve a one-note shift when the driver
    plays the same note on several channels in the same tick (Auckland scores
    96 % two events away from the truth), so the coarse offset is re-scored
    against the full event sequence."""
    skip = ('dac',)
    ref = [t for t in ref_tokens if t[0] not in skip][:window]
    if not ref:
        return off
    best, best_score = off, -1.0
    for cand in range(max(0, off - span), min(len(port_tokens) - 1, off + span) + 1):
        sub = [t for t in port_tokens[cand:cand + window * 2] if t[0] not in skip][:window]
        if not sub:
            continue
        score, _d, _e = sequence_match(ref, sub, top=0)
        if score > best_score:
            best, best_score = cand, score
    return best


def token_index_of_key(tokens, key_index):
    """Token index of the n-th key event in a token list."""
    n = 0
    for i, t in enumerate(tokens):
        if t[0] in ('keyon', 'keyoff'):
            if n == key_index:
                return i
            n += 1
    return len(tokens)


def class_of(tok):
    return tok[0]


def sequence_match(ref, port, lookahead=48, top=8):
    """Bounded-lookahead diff of two token sequences.

    difflib is unusable here (tens of thousands of highly repetitive tokens:
    minutes of CPU for one comparison), so this walks both lists and resyncs
    on the smallest insertion, deletion or replacement within `lookahead`
    tokens. The reported ratio is difflib's definition,
    2*matches/(len(ref)+len(port)), and the first divergences carry enough
    context to identify the note, patch or channel that differs."""
    i = j = matches = 0
    divs = []
    eq = []
    while i < len(ref) and j < len(port):
        if ref[i] == port[j]:
            matches += 1
            eq.append((i, j))
            i += 1
            j += 1
            continue
        found = None
        for k in range(1, lookahead + 1):
            if i + k < len(ref) and ref[i + k] == port[j]:
                found = ('delete', k, 0)
                break
            if j + k < len(port) and ref[i] == port[j + k]:
                found = ('insert', 0, k)
                break
            if (i + k < len(ref) and j + k < len(port)
                    and ref[i + k] == port[j + k]):
                found = ('replace', k, k)
                break
        if found is None:
            found = ('replace', 1, 1)
        kind, di, dj = found
        if len(divs) < top:
            divs.append(dict(kind=kind, ref_index=i, ref_count=di,
                             port_index=j, port_count=dj,
                             ref=[list(map(str, t)) for t in ref[i:i + max(di, 1)]],
                             port=[list(map(str, t)) for t in port[j:j + max(dj, 1)]]))
        i += di
        j += dj
    if i < len(ref) or j < len(port):
        if len(divs) < top:
            divs.append(dict(kind='tail', ref_index=i, ref_count=len(ref) - i,
                             port_index=j, port_count=len(port) - j,
                             ref=[list(map(str, t)) for t in ref[i:i + 1]],
                             port=[list(map(str, t)) for t in port[j:j + 1]]))
    total = len(ref) + len(port)
    return (2.0 * matches / total if total else 1.0), divs, eq


def logic_compare(ref_tokens, port_tokens, offset, top=8, skip=('dac',)):
    """Ordered-token comparison. `skip` classes are reported but excluded from
    the overall ratio: the port's DAC stream is orders of magnitude larger than
    the rip's and would otherwise swamp every other class."""
    sub = port_tokens[offset:]
    ref_cmp = [t for t in ref_tokens if t[0] not in skip]
    port_cmp = [t for t in sub if t[0] not in skip]
    overall, divergences, _eq = sequence_match(ref_cmp, port_cmp, top=top)
    per_class = {}
    for cls in CLASS_ORDER:
        a = [t for t in ref_tokens if t[0] == cls]
        b = [t for t in sub if t[0] == cls]
        if not a and not b:
            continue
        m, _d, _e = sequence_match(a, b, top=0) if a and b else (0.0, [], [])
        per_class[cls] = dict(ref=len(a), port=len(b), match=m)
    return dict(match=overall, per_class=per_class, divergences=divergences,
                ref_tokens=len(ref_cmp), port_tokens=len(port_cmp),
                skipped=list(skip))


def pair_events(ref, port):
    """Matched (t_ref, t_port) key events, from the bounded diff of the trains.

    Index pairing alone would drift by one event for every missing note, so the
    pairs come from the same resync walk the logic comparison uses."""
    sig_ref = [(e[1], e[2], e[3]) for e in ref]
    sig_port = [(e[1], e[2], e[3]) for e in port]
    _m, _d, eq = sequence_match(sig_ref, sig_port, top=0)
    return [(ref[i][0], port[j][0]) for i, j in eq]


def robust_regress(pairs, rounds=4):
    """Fit, drop points further than 4 MADs from the line, refit."""
    cur = list(pairs)
    r = regress(cur)
    for _ in range(rounds):
        if not r or len(cur) < 8:
            break
        res = [p[1] - (r['intercept'] + r['slope'] * p[0]) for p in cur]
        med = statistics.median(res)
        mad = statistics.median([abs(x - med) for x in res]) or 1e-6
        keep = [p for p, e in zip(cur, res) if abs(e - med) < 4.0 * 1.4826 * mad]
        if len(keep) == len(cur) or len(keep) < 8:
            break
        cur = keep
        r = regress(cur)
    if r:
        r['outliers_dropped'] = len(pairs) - len(cur)
    return r


def regress(pairs):
    """Least squares t_port = a + b * t_ref, plus rms residual."""
    n = len(pairs)
    if n < 4:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    if sxx <= 0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    b = sxy / sxx
    a = my - b * mx
    res = [p[1] - (a + b * p[0]) for p in pairs]
    return dict(slope=b, intercept=a,
                rms_ms=math.sqrt(sum(r * r for r in res) / n) * 1e3,
                n=n, span_s=pairs[-1][0] - pairs[0][0])


def local_ratio(pairs, window=1.0, min_pairs=12):
    """Sliding regression slope per second of reference time."""
    out = []
    if not pairs:
        return out
    t0, t1 = pairs[0][0], pairs[-1][0]
    k = 0
    start = t0
    while start + window <= t1:
        lo, hi = start, start + window
        seg = [p for p in pairs if lo <= p[0] < hi]
        if len(seg) >= min_pairs:
            r = regress(seg)
            if r and r['slope'] > 0:
                out.append((start, 1.0 / r['slope']))
        start += window
    return out


def detect_loop(keyons, min_seconds=10.0, probe=200, min_score=0.97):
    """Loop period of a key-on train: best self-match lag, in seconds.

    Only reported when the train really repeats (>= min_score of the probe).
    Top Gear 2's phrases repeat about 1 % away from the true loop, which is the
    same aliasing that defeated task 18's envelope alignment, so a weak match
    is reported as "not resolvable" instead of as a loop."""
    n = len(keyons)
    if n < 4 * probe:
        return None
    best = None
    for lag in range(probe, n // 2):
        if keyons[lag][0] - keyons[0][0] < min_seconds:
            continue
        score = 0
        for k in range(probe):
            a = keyons[k]
            b = keyons[k + lag]
            if a[1] == b[1] and a[2] == b[2] and a[3] == b[3]:
                score += 1
        if best is None or score > best[1]:
            best = (lag, score)
        if score >= probe * 0.98:
            break
    if not best or best[1] < probe * min_score:
        return None
    lag = best[0]
    period = keyons[lag][0] - keyons[0][0]
    return dict(lag_events=lag, period_s=period, score=best[1] / probe)


# ------------------------------------------------------------------- report
def compare(ref, port, label='', quiet=False):
    ref_regs = ref.regs()
    port_regs = port.regs()
    ref_ticks = timer_ticks(ref_regs)
    port_ticks = timer_ticks(port_regs)
    ref_keys = key_events(ref_regs)
    port_keys = key_events(port_regs)
    ref_tokens, ref_times = logic_tokens(ref_regs, with_times=True)
    port_tokens, port_times = logic_tokens(port_regs, with_times=True)

    key_off, key_score = align_keyons(ref_keys, port_keys)
    off = token_index_of_key(port_tokens, key_off)
    off = refine_offset(ref_tokens, port_tokens, off)
    pairs = pair_events(ref_keys, port_keys[key_off:])
    reg = robust_regress(pairs)
    local = local_ratio(pairs)

    # Compare the same musical span on both sides: cut whichever side is
    # longer at the other side's last tick, otherwise the extra music counts as
    # insertions and drags the match ratio down.
    cut = len(port_tokens)
    ref_keep = len(ref_tokens)
    # The port capture starts at boot, so it carries ticks of whatever played
    # before the route reached this song (the title theme). The alignment above
    # found where the reference's first key event sits in the port, so count
    # ticks from there before matching spans.
    tick_off = 0
    if key_off < len(port_keys):
        t_song = port_keys[key_off][0]
        while tick_off < len(port_ticks) and port_ticks[tick_off] < t_song:
            tick_off += 1
    port_song_ticks = len(port_ticks) - tick_off
    if port_song_ticks >= len(ref_ticks) >= 2:
        port_end = port_ticks[tick_off + len(ref_ticks) - 1] + 0.02
        cut = 0
        while cut < len(port_times) and port_times[cut] <= port_end:
            cut += 1
    elif len(ref_ticks) > port_song_ticks >= 2:
        ref_end = ref_ticks[port_song_ticks - 1] + 0.02
        ref_keep = 0
        while ref_keep < len(ref_times) and ref_times[ref_keep] <= ref_end:
            ref_keep += 1
    logic = logic_compare(ref_tokens[:ref_keep], port_tokens[:cut], off)
    logic['align_key_score'] = key_score
    logic['span_seconds'] = pairs[-1][0] - pairs[0][0] if pairs else 0.0

    rt = tick_stats(ref_ticks)
    pt = tick_stats(port_ticks)

    res = dict(label=label, reference=ref.meta, port=port.meta,
               logic=logic, align_offset=off,
               ticks=dict(reference=rt, port=pt))

    # global tempo ratios
    ratios = {}
    if rt.get('mean_ms') and pt.get('mean_ms'):
        ratios['tick_mean'] = rt['mean_ms'] / pt['mean_ms']
    if rt.get('median_ms') and pt.get('median_ms'):
        ratios['tick_median'] = rt['median_ms'] / pt['median_ms']
    if reg:
        # t_port = a + slope * t_ref, so the port's speed is 1/slope
        ratios['keyon_regression'] = 1.0 / reg['slope']
    ref_loop = ref.meta.get('loop_seconds') or 0.0
    if ref_loop > 1.0:
        port_loop = detect_loop(port_keys, min_seconds=ref_loop * 0.8)
        if port_loop:
            ratios['loop_period'] = ref_loop / port_loop['period_s']
            res['loop'] = dict(reference_s=ref_loop, port=port_loop)
    res['ratios'] = ratios
    if ratios:
        errs = [(k, (v - 1.0) * 100.0) for k, v in ratios.items()]
        res['error_pct'] = dict(errs)
        res['worst_error_pct'] = max(errs, key=lambda kv: abs(kv[1]))
    if reg:
        res['regression'] = reg
    if local:
        slopes = [s for _t, s in local]
        s = sorted(slopes)
        res['local'] = dict(windows=len(slopes),
                            mean_pct=(statistics.mean(slopes) - 1) * 100,
                            std_pct=statistics.pstdev(slopes) * 100,
                            p05_pct=(s[len(s) // 20] - 1) * 100,
                            p95_pct=(s[-len(s) // 20] - 1) * 100,
                            max_dev_pct=max(abs(x - 1) for x in slopes) * 100,
                            worst=[(round(t, 2), round((v - 1) * 100, 3))
                                   for t, v in sorted(local, key=lambda kv: -abs(kv[1] - 1))[:5]])
    if not quiet:
        print_report(res)
    return res


def print_report(res):
    m = res['reference']
    p = res['port']
    print('=' * 78)
    print('reference : %s' % m.get('path', '?'))
    if m.get('kind') == 'vgm':
        g = m.get('gd3', {})
        print('            VGM %s, YM2612 %d Hz, %.2f s, loop %.2f s'
              % (m.get('version'), m.get('ym_clock', 0), m.get('seconds', 0),
                 m.get('loop_seconds', 0)))
        if g:
            print('            GD3: track=%r game=%r system=%r date=%r ripper=%r'
                  % (g.get('track', ''), g.get('game', ''), g.get('system', ''),
                     g.get('date', ''), g.get('ripper', '')))
        if m.get('reserved'):
            print('            reserved/no-op command bytes: %s'
                  % ', '.join('0x%02X x%d' % (k, v) for k, v in sorted(m['reserved'].items())))
    print('port      : %s' % p.get('path', '?'))
    if p.get('kind') == 'writedump':
        print('            %d chip writes (z80 %d, 68k %d), frames %d..%d, %.2f s'
              % (p['writes'], p['z80_writes'], p['m68k_writes'],
                 p['first_frame'], p['last_frame'], p['seconds']))

    t = res['ticks']
    print('\ntimer-B ticks ($27 load writes)')
    for side in ('reference', 'port'):
        s = t[side]
        if 'mean_ms' not in s:
            print('  %-9s n=%d (too few)' % (side, s.get('count', 0)))
            continue
        print('  %-9s n=%4d  mean %7.3f ms  median %7.3f  p05 %7.3f  p95 %7.3f  '
              '%6.2f ticks/s' % (side, s['count'], s['mean_ms'], s['median_ms'],
                                 s['p05_ms'], s['p95_ms'], s['rate_hz']))

    print('\ntempo ratio (port / reference; >1 means the port is faster)')
    for k, v in sorted(res.get('ratios', {}).items()):
        print('  %-16s %.6f  (%+0.3f %%)' % (k, v, (v - 1) * 100))
    if res.get('loop'):
        print('  loop: reference %.3f s, port %.3f s (matched %d events, %.0f%% of the probe)'
              % (res['loop']['reference_s'], res['loop']['port']['period_s'],
                 res['loop']['port']['lag_events'], res['loop']['port']['score'] * 100))
    if res.get('regression'):
        r = res['regression']
        print('  key-on regression: %d pairs over %.1f s, rms residual %.1f ms'
              % (r['n'], r['span_s'], r['rms_ms']))
    if res.get('local'):
        l = res['local']
        print('  local (1 s windows): n=%d mean %+0.3f %% std %0.3f %% p05 %+0.3f %% '
              'p95 %+0.3f %% max |dev| %0.3f %%'
              % (l['windows'], l['mean_pct'], l['std_pct'], l['p05_pct'],
                 l['p95_pct'], l['max_dev_pct']))
        if l['worst']:
            print('  worst windows (t s, %%): %s' % l['worst'])

    lg = res['logic']
    print('\nlogic (ordered events, timing ignored): %.2f %% match '
          '(DAC excluded), key alignment %.1f %%, offset %d'
          % (lg['match'] * 100, lg['align_key_score'] * 100, res['align_offset']))
    print('  %-8s %8s %8s %7s' % ('class', 'ref', 'port', 'match'))
    for cls in CLASS_ORDER:
        c = lg['per_class'].get(cls)
        if not c:
            continue
        print('  %-8s %8d %8d %6.2f %%' % (cls, c['ref'], c['port'], c['match'] * 100))
    if lg['divergences']:
        print('  first divergences:')
        for d in lg['divergences']:
            print('    %-7s ref[%d..%d]=%s  port[%d..%d]=%s'
                  % (d['kind'], d['ref_index'], d['ref_index'] + d['ref_count'],
                     d['ref'], d['port_index'], d['port_index'] + d['port_count'], d['port']))
    print('=' * 78)


# --------------------------------------------------------------- ticklog
def read_ticklog(path):
    """GENESIS_YM_TICKLOG: per-timer-write Z80 cycle total and BUSREQ lines."""
    rows = []
    for line in open(path):
        kv = dict(x.split('=') for x in line.split())
        rows.append(dict(now=int(kv['now']), cyc=int(kv['cyc']),
                         busreq=int(kv['busreq_lines']),
                         val=int(kv['val'], 16)))
    return rows


def ticklog_report(path, period_ms=None):
    rows = read_ticklog(path)
    rel = [r for r in rows if r['val'] & T27_LOAD_B]
    out = dict(ticks=len(rel))
    if len(rel) < 3:
        return out
    wall, cyc = [], []
    for a, b in zip(rel, rel[1:]):
        dt = (b['now'] - a['now']) / MASTER_CLOCK
        dz = (b['cyc'] - a['cyc']) / 3579545.0
        if 0 < dt < 0.1:
            wall.append(dt)
            cyc.append(dz)
    if not wall:
        return out
    out['mean_wall_ms'] = statistics.mean(wall) * 1e3
    out['mean_z80_ms'] = statistics.mean(cyc) * 1e3
    out['z80_share'] = statistics.mean(cyc) / statistics.mean(wall)
    out['busreq_lines'] = rel[-1]['busreq']
    out['busreq_per_tick'] = (rel[-1]['busreq'] - rel[0]['busreq']) / len(rel)
    print('\nZ80 cycle accounting (GENESIS_YM_TICKLOG)')
    print('  ticks %d, wall %.3f ms/tick, Z80 %.3f ms/tick -> %.2f %% of the '
          'Z80 budget delivered' % (out['ticks'], out['mean_wall_ms'],
                                    out['mean_z80_ms'], out['share'] * 100
                                    if 'share' in out else out['z80_share'] * 100))
    print('  BUSREQ-held scanlines: %d total, %.2f per tick'
          % (out['busreq_lines'], out['busreq_per_tick']))
    return out


# --------------------------------------------------------------- selftest
def _synth_events(seconds=40.0, period=19.83e-3, seed=1):
    """A deterministic driver-like event list: ticks, key-ons, freqs, patches."""
    import random
    rnd = random.Random(seed)
    ev = []
    t = 0.0
    tick = 0
    while t < seconds:
        ev.append((t, 0, 0x27, 0x2E))                     # timer reload
        if tick % 6 == 0:
            ch = (tick // 6) % 6
            ev.append((t + 0.001, 0, 0x28, ch & 3 | (0x04 if ch >= 3 else 0) | 0x30))
            ev.append((t + 0.002, 0 if ch < 3 else 1,
                       0xA4 + (ch % 3) if ch < 3 else 0xAC + (ch % 3),
                       ((2 + (tick // 24) % 3) << 3) | rnd.randrange(0, 8)))
            ev.append((t + 0.003, 0 if ch < 3 else 1, 0xA0 + (ch % 3),
                       rnd.randrange(0, 256)))
            ev.append((t + 0.004, 0, 0x28, ch & 3 | (0x04 if ch >= 3 else 0)))
        ev.append((t + 0.005, 0, 0x40 + (tick % 4), rnd.randrange(0, 128)))
        t += period
        tick += 1
    return ev


def _write_vgm(events, path, loop_s=None):
    body = bytearray()
    samp = 0
    latch = [0, 0]
    for t, bank, reg, val in events:
        target = int(round(t * VGM_RATE))
        if target > samp:
            while target - samp > 0:
                n = min(target - samp, 65535)
                body += bytes((0x61, n & 0xFF, n >> 8))
                samp += n
        body += bytes((0x52 + bank, reg, val))
    total = samp
    head = bytearray(0x40)
    head[0:4] = b'Vgm '
    struct.pack_into('<I', head, 8, 0x150)
    struct.pack_into('<I', head, 0x18, total)
    struct.pack_into('<I', head, 0x2C, 7670453)
    struct.pack_into('<I', head, 0x34, 0x0C)
    data = bytes(head) + bytes(0x0C) + bytes(body) + b'\x66'
    open(path, 'wb').write(data)


def _write_dump(events, path, scale=1.0, jitter=0.0, seed=3):
    import random
    rnd = random.Random(seed)
    lines = []
    for t, bank, reg, val in events:
        tt = t * scale + (rnd.uniform(-jitter, jitter) if jitter else 0.0)
        mc = int(round(tt * MASTER_CLOCK))
        frame, off = divmod(mc, MASTER_PER_FRAME)
        lines.append('f=%d sl=%d FM  p%d $%02X mc=%d wf=%d pcz=$0CB2'
                     % (frame, off // 3420, bank * 2, reg, off, frame))
        lines.append('f=%d sl=%d FM  p%d $%02X mc=%d wf=%d pcz=$0C4C'
                     % (frame, off // 3420, bank * 2 + 1, val, off, frame))
    open(path, 'w').write('\n'.join(lines) + '\n')


def selftest(tmp='/tmp'):
    import os
    ok = True
    ev = _synth_events()
    ref = os.path.join(tmp, 'vgm_compare_ref.vgm')
    _write_vgm(ev, ref, loop_s=20.0)
    for scale, want in ((1.015, 1.015), (0.990, 0.990), (1.0, 1.0)):
        port = os.path.join(tmp, 'vgm_compare_port.txt')
        _write_dump(ev, port, scale=1.0 / scale)
        r = compare(read_vgm(ref), read_writedump(port), quiet=True)
        got = r['ratios'].get('keyon_regression', 0.0)
        err = abs(got - want) * 100
        print('selftest scale %.3f: regression %.6f (want %.6f), logic %.2f %% match'
              % (scale, got, want, r['logic']['match'] * 100))
        if err > 0.02 or r['logic']['match'] < 0.999:
            ok = False
    # a wrong note must be caught
    bad = [(t, b, r_, v) for (t, b, r_, v) in ev]
    bad[400] = (bad[400][0], bad[400][1], bad[400][2], bad[400][3] ^ 0x0F)
    port = os.path.join(tmp, 'vgm_compare_port.txt')
    _write_dump(bad, port)
    r = compare(read_vgm(ref), read_writedump(port), quiet=True)
    print('selftest corruption: logic %.2f %% match, first divergence %s'
          % (r['logic']['match'] * 100,
             (r['logic']['divergences'] or [{}])[0].get('kind', 'none')))
    if not r['logic']['divergences']:
        ok = False
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vgm')
    ap.add_argument('--dump')
    ap.add_argument('--ticklog')
    ap.add_argument('--label', default='')
    ap.add_argument('--json')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.vgm or not a.dump:
        ap.error('--vgm and --dump are required (or --selftest)')
    ref = read_vgm(a.vgm)
    port = read_writedump(a.dump)
    res = compare(ref, port, label=a.label)
    if a.ticklog:
        res['ticklog'] = ticklog_report(a.ticklog)
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(res, f, indent=1, default=str)
    return 0


if __name__ == '__main__':
    sys.exit(main())
