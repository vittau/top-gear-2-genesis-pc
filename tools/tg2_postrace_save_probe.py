#!/usr/bin/env python3
"""Can a quickstate be saved on the inter-race screens?

Finishes one race with the closed-loop driver, then, on every screen of the
post-race flow (results, championship table, shop, next-track intro, countdown),
requests a quickstate save through the same runner path the menu and the hotkey
use, and records whether it was written or refused. Each attempt waits past the
engine's 120-frame boundary timeout, so a refusal here is the same refusal a
player sees as `SAVE UNAVAILABLE HERE`.

  python3 tools/tg2_postrace_save_probe.py --port 4660 \
      --out build/qual/postrace-saves --country 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg2_runner import Runner, KEYS, manifest_counts  # noqa: E402
from tg2_race_driver import Driver  # noqa: E402
import tg2_password as pw  # noqa: E402
from tg2_password_ui import PasswordUI  # noqa: E402
from tg2_progress import NitroDriver, driver_args, UPGRADES  # noqa: E402


class Probe:
    def __init__(self, runner: Runner):
        self.r = runner
        self.err = runner.out / 'stderr.log'
        self.err_off = self.err.stat().st_size if self.err.exists() else 0

    def new_lines(self):
        if not self.err.exists():
            return []
        with self.err.open(errors='replace') as f:
            f.seek(self.err_off)
            text = f.read()
            self.err_off = f.tell()
        return text.splitlines()

    def signals(self):
        r = self.r
        return {
            'frame': r.frame(),
            'phase': r.ram8(0x1866),
            'race_index': r.ram16(0x16BE),
            'clock': r.state_and_frame().clock,
            'picture_count': r.ram16(0x23B4),
            'mode_1e00': r.ram8(0x1E00),
        }

    def rdb_dump(self, label: str, frames: int = 20):
        r = self.r
        r.command('rdb_reset')
        r.command('rdb_range', lo='0xFF0000', hi='0xFFFFFF')
        r.wait_frame(r.frame() + frames)
        out = []
        start = 0
        while True:
            reply = r.command('rdb_dump', start=start, count=20000, timeout=60.0)
            out.extend(reply['log'])
            if reply['done']:
                break
            start += reply['returned']
        p = self.r.out / f'rdb-{label.replace(" ", "_").replace("/", "_")}.json'
        p.write_text(__import__('json').dumps(out))
        return str(p), len(out)

    def save(self, path: Path, label: str, wait: int = 150):
        """Ask for a quickstate; the file may appear only after the flow moves
        on (a queued save waits for the next resumable boundary)."""
        path.unlink(missing_ok=True)
        before = self.signals()
        self.new_lines()
        queued = False
        try:
            self.r.command('save_state', path=str(path))
            queued = True
        except RuntimeError:
            queued = False
        stop = self.r.frame() + wait
        while self.r.frame() < stop:
            time.sleep(0.004)
        lines = self.new_lines()
        saved = path.exists() and path.stat().st_size > 0
        after = self.signals()
        return {
            'screen': label,
            'before': before,
            'after': after,
            'queued': queued,
            'written': saved,
            'size': path.stat().st_size if saved else None,
            'log': [l for l in lines if l.startswith('[SAVE]') or l.startswith('[LOAD]')],
        }

    def settle(self, record, path: Path, frames: int = 400):
        """After the flow advances, note whether a queued save has landed."""
        stop = self.r.frame() + frames
        while self.r.frame() < stop:
            time.sleep(0.004)
        record['written_after_advance'] = path.exists() and path.stat().st_size > 0
        record['size_after_advance'] = path.stat().st_size if path.exists() else None
        record['log'] += [l for l in self.new_lines()
                          if l.startswith('[SAVE]') or l.startswith('[LOAD]')]
        return record


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=4660)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--country', type=int, default=4)
    p.add_argument('--stage', type=int, default=0)
    p.add_argument('--money', type=int, default=150)
    p.add_argument('--rom', type=Path, default=Path.home() / 'roms/genesis/tg2.bin')
    p.add_argument('--exe', type=Path,
                   default=Path(__file__).resolve().parents[1] / 'build/TG2Recomp')
    p.add_argument('--realtime', dest='turbo', action='store_false', default=True)
    p.add_argument('--steps', type=int, default=12,
                   help='START taps to walk through after the finish')
    p.add_argument('--kp', type=float, default=1.0)
    p.add_argument('--kd', type=float, default=4.0)
    p.add_argument('--kc', type=float, default=0.0)
    p.add_argument('--deadband', type=float, default=9.0)
    p.add_argument('--target-lat', type=float, default=0.0)
    p.add_argument('--launch-delay', type=int, default=0)
    p.add_argument('--post-frames', type=int, default=4000)
    p.add_argument('--post-interval', type=int, default=110)
    p.add_argument('--yield-log', action='store_true',
                   help='pass --yield-log and keep the WaitForVint park log')
    p.add_argument('--rdb', action='store_true',
                   help='dump the reverse-debug write log at every screen')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    fields = dict(country=a.country, stage=a.stage, money=a.money)
    fields.update({name: (7 if name in ('u52', 'u54') else 3) for name in UPGRADES})
    password = pw.encode(**fields)
    da = driver_args(a)
    evidence = {'country': a.country, 'result': 'error', 'attempts': [], 'shots': []}

    args = ['--turbo'] if a.turbo else []
    env = {}
    if a.yield_log:
        args.append('--yield-log')
        env['GENESIS_YIELD_LOG'] = str((a.out / 'yield.log').resolve())
    r = Runner(port=a.port, out=a.out, exe=a.exe, rom=a.rom, widescreen='off',
               max_frames=400000, extra_args=args, env_extra=env,
               video_driver='dummy')
    probe = Probe(r)
    d = NitroDriver(r, da)
    slot = (a.out / 'postrace-state.bin').resolve()
    try:
        r.start()
        ui = PasswordUI(r, a)
        ui.to_password_screen()
        ui.type_symbols(password['symbols'])
        ui.submit()
        r.wait_frame(r.frame() + 200)
        ui.tap('START', 7, 50)                       # RACE row -> intro panel
        st = d.press_start_until_race(label='pre-race', prev_clock=None)
        if st is None:
            evidence['result'] = 'no-race'
            raise SystemExit(json.dumps(evidence, indent=2))
        d.shot('race-start')
        if a.rdb:
            path, entries = probe.rdb_dump('race-running')
            evidence.setdefault('rdb', []).append(dict(screen='race (running)',
                                                       path=path, entries=entries))
        evidence['attempts'].append(probe.save(slot, 'race (running)'))
        race = d.drive_race(da)
        d.shot('finish')
        evidence['race'] = {k: race.get(k) for k in
                            ('start_frame', 'finish_frame', 'finish_clock', 'timeout')}
        if race.get('timeout'):
            evidence['result'] = 'timeout'
            raise SystemExit(json.dumps(evidence, indent=2))
        frozen = race['finish_clock']

        # Screen 0 is the moment the finish is detected; then one START tap per
        # screen, saving on each before advancing.
        d.shot('post-00')
        rec = probe.save(slot, 'after finish (results?)')
        evidence['attempts'].append(rec)
        reached_countdown = False
        for step in range(1, a.steps + 1):
            d.tap('START', 7)
            stop = r.frame() + 300
            while r.frame() < stop:
                s = d.state()
                if s.clock < frozen:
                    reached_countdown = True
                    break
                time.sleep(0.004)
            probe.settle(rec, slot)
            d.shot(f'post-{step:02d}')
            if a.rdb:
                path, entries = probe.rdb_dump(f'post-{step:02d}')
                evidence.setdefault('rdb', []).append(dict(screen=f'post-{step:02d}',
                                                           path=path, entries=entries))
            if reached_countdown:
                rec = probe.save(slot, f'next race countdown (tap {step})')
                evidence['attempts'].append(rec)
                break
            rec = probe.save(slot, f'post-race screen {step}')
            evidence['attempts'].append(rec)
        evidence['reached_countdown'] = reached_countdown

        # Let the new race run, then save inside it (control).
        r.wait_frame(r.frame() + 400)
        d.shot('race-2-running')
        evidence['attempts'].append(probe.save(slot, 'race 2 (running, control)'))
        evidence['result'] = 'done'
    finally:
        code = r.stop()
        evidence['exit_code'] = code
        evidence['manifests'] = manifest_counts(a.out)
        evidence['shots'] = d.shots
        (a.out / 'summary.json').write_text(json.dumps(evidence, indent=2) + '\n')
        for at in evidence['attempts']:
            print(json.dumps({k: at.get(k) for k in
                              ('screen', 'queued', 'written', 'size',
                               'written_after_advance', 'size_after_advance')}))
        print(json.dumps({'result': evidence['result'], 'exit': code,
                          'manifests': evidence['manifests']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
