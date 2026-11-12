#!/usr/bin/env python3
"""High-resolution ground-truth probe: per-line road state and scene dumps.

Drives the stock game into a race through its own password screen, then samples
read-only presentation state while racing:

  * `tg2_video` `{"rows":1}` — every race row's plane-A/B H-scroll, VSRAM and
    plane bases (the state `game/tg2_video.c` rerenders each line from);
  * the player record's road snapshot (`$FF18CA+$70..$86`), the sampled
    segment pointer and the road tables the road renderer reads;
  * VRAM plane B (`$E000`, 8 KiB), the H-scroll table (`$B800`) and the
    displayed SAT (`$BE00`);
  * reference PNGs at the first and last sample.

Nothing is written to the guest: the runner's read-only commands only.

  python3 tools/highres_probe.py --port 4640 --out build/highres/road-c00 \
      --country 0 --seconds 40 --every 120
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner  # noqa: E402
from tg2_coverage import Coverage, manifests  # noqa: E402

PLAYER = 0x18CA

# Words the picture build / road renderer reads (RAM_MAP.md + disassembly).
ROAD_RAM = {
    0x1866: 1,   # race phase
    0x1878: 1,   # special mapping mode ($FD66 / $FFFE)
    0x1894: 1,   # LOD/size bias word (-$6b74)
    0x189E: 1,   # two-player flag
    0x1996: 2,   # sampled segment-table base (long)
    0x1DBE: 1,   # road width/scale word (-$664a)
    0x1DB0: 1,
    0x1DE0: 1,
    0x17BC: 1,   # horizon/screen limit (-$6c4c)
    0x17D6: 1,   # (-$6c32)
    0x17D8: 1,   # (-$6c30)
    0x17DA: 1,   # (-$6c2e)
    0x22FE: 1,   # object type (-$610a)
    0x2452: 1,   # plane-A scroll base
}

# Player record fields the picture snapshot copies.
PLAYER_FIELDS = {
    0x00: ('pos', 2),
    0x04: ('lat', 2),
    0x08: ('view', 2),
    0x0E: ('speed', 1),
    0x12: ('segment', 1),
    0x14: ('curve', 1),
    0x16: ('slope', 1),
    0x20: ('steer_input', 1),
    0x52: ('state', 1),
    0x70: ('snap_steer', 1),
    0x74: ('snap_pos', 2),
    0x78: ('snap_second', 2),
    0x7C: ('snap_view', 2),
    0x80: ('snap_state', 1),
    0x84: ('snap_slope', 1),
    0x86: ('snap_curve', 1),
}


def be16(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off:off + 2], 'big')


def be32(buf: bytes, off: int) -> int:
    return int.from_bytes(buf[off:off + 4], 'big')


def sample(r: Runner, name: str, shot: bool = False) -> dict:
    frame = r.frame()
    rows = r.command('tg2_video', rows=1)
    rec = r.ram(PLAYER, 0x90)
    words = {f'0x{a:04X}': be16(r.ram(a, 2), 0) for a in ROAD_RAM if ROAD_RAM[a] == 1}
    longs = {f'0x{a:04X}': be32(r.ram(a, 4), 0) for a in ROAD_RAM if ROAD_RAM[a] == 2}
    item = {
        'name': name,
        'frame': frame,
        'rows': rows.get('rows'),
        'wide_lines': rows.get('wide_lines'),
        'native_lines': rows.get('native_lines'),
        'hud_edges': rows.get('hud_edges'),
        'ram_words': words,
        'ram_longs': longs,
        'player': {f: (be32(rec, off) if wide == 2 else be16(rec, off))
                   for off, (f, wide) in PLAYER_FIELDS.items()},
        'vram': ''.join(r.vram(a, 0x1000).hex() for a in range(0, 0x10000, 0x1000)),
        'cram': r.command('read_cram')['hex'],
        'vram_hscroll': r.vram(0xB800, 0x380).hex(),
        'vram_sat': r.vram(0xBE00, 0x280).hex(),
        'ram_head': r.ram(0x18CA, 0x100).hex(),
        'wram': (''.join(r.ram(a, 0x1000).hex() for a in range(0, 0x10000, 0x1000))
                 if shot else None),
        'ram_road_tables': r.ram(0x1D00, 0x100).hex(),
    }
    if shot:
        item['shot'] = str(r.screenshot(f'{name}.png'))
    return item


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4640)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=0)
    p.add_argument('--stage', type=int, default=0)
    p.add_argument('--seconds', type=float, default=40.0)
    p.add_argument('--every', type=int, default=120)
    p.add_argument('--samples', type=int, default=0,
                   help='stop after this many samples (0 = every --every frame)')
    p.add_argument('--exe', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'build/TG2Recomp')
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(
        country=a.country, stage=a.stage, mode='off', port=a.port, out=a.out,
        kp=1.0, kd=4.0, kc=0.0, deadband=9.0, target_lat=0.0, nitro=False,
        nitro_at=10**9, nitro_for=0, shot_every=600)
    r = Runner(port=a.port, out=a.out, exe=a.exe, rom=a.rom, widescreen='off',
               max_frames=200000,
               env_extra={'TG2_HIDE_OVERSCAN': '0'},
               extra_args=['--turbo'], video_driver='dummy')
    samples = []
    result = 'error'
    try:
        r.start()
        cov = Coverage(r, args)
        cov.ui.to_password_screen()
        import tg2_password as pw
        cov.ui.type_symbols(pw.encode(country=a.country, stage=a.stage)['symbols'])
        cov.ui.submit()
        st = cov.press_until_race()
        if st is None:
            result = 'no-race'
        else:
            result = 'ok'
            start = st.frame
            frames = int(a.seconds * 60)
            last = None
            shots = 0
            while r.frame() - start < frames:
                now = r.frame()
                if now - start >= 300 and (last is None or now - last >= a.every):
                    last = now
                    name = f'sample-{len(samples):03d}'
                    samples.append(sample(r, name, shot=shots < 2))
                    if shots < 2:
                        shots += 1
                    if a.samples and len(samples) >= a.samples:
                        break
                # Full throttle, straight: the route only needs motion.
                r.set_input(0x10)
                r.wait_frame(r.frame() + 10)
            r.set_input(0)
    finally:
        code = r.stop()
    (a.out / 'samples.json').write_text(json.dumps(samples) + '\n')
    summary = dict(result=result, samples=len(samples), exit_code=code,
                   manifests=manifests(a.out), files=sorted(p.name for p in a.out.iterdir()))
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
    return 0 if result == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
