#!/usr/bin/env python3
"""Small library for driving one native TG2Recomp process over its TCP server.

Only read-only state is used (RAM/VRAM dumps, screenshots, frame_info); input is
controller input via `set_input`. Every helper refuses to touch a process it did
not launch, and the port guard keeps parallel worktrees apart.

Usage as a library:

    from tg2_runner import Runner, KEYS
    with Runner(port=4470, out='build/qual/x') as r:
        r.wait_frame(600)
        r.tap('START', 8)
        print(r.ram(0x18CA, 4).hex())

This module deliberately has no side-channel into the guest: no WRITE_RAM, no
save states, no `pause`-and-poke. Qualification must prove the real game flow.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / 'build' / 'TG2Recomp'
DEFAULT_ROM = Path.home() / 'roms/genesis/tg2.bin'
DEFAULT_PORT = 4470

# Genesis pad bit order used by the runner's set_input and input_script.
KEYS = {'UP': 0x01, 'DOWN': 0x02, 'LEFT': 0x04, 'RIGHT': 0x08,
        'B': 0x10, 'C': 0x20, 'A': 0x40, 'START': 0x80}
BUTTON_ORDER = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'B', 'C', 'A', 'START']


def mask(*names: str) -> int:
    value = 0
    for name in names:
        value |= KEYS[name]
    return value


def port_is_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


class Runner:
    def __init__(self, port: int = DEFAULT_PORT, out: str | Path = ROOT / 'build/qual/run',
                 exe: str | Path = DEFAULT_EXE, rom: str | Path = DEFAULT_ROM,
                 widescreen: str = 'off', max_frames: int = 100000,
                 env_extra: dict | None = None, extra_args: list[str] | None = None,
                 fresh: bool = True, timeout: float = 60.0,
                 video_driver: str = 'dummy'):
        self.port = int(port)
        self.out = Path(out).resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.exe = Path(exe).resolve()
        self.rom = Path(rom).resolve()
        self.widescreen = widescreen
        self.max_frames = max_frames
        self.env_extra = dict(env_extra or {})
        self.extra_args = list(extra_args or [])
        self.fresh = fresh
        self.timeout = timeout
        # 'offscreen' has no emulated vblank wait, which is what makes an
        # uncapped (--turbo) replay fast; 'dummy' paces at 60 Hz like a display.
        self.video_driver = video_driver
        self.proc: subprocess.Popen | None = None
        self.request_id = 0
        self.commands = 0
        self._out_file = None
        self._err_file = None

    # -- lifecycle -----------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False

    def start(self):
        if not port_is_free(self.port):
            raise RuntimeError(f'TCP port {self.port} is already in use; stop its owner first')
        (self.exe.parent / 'debug.ini').touch()
        env = dict(os.environ, SDL_VIDEODRIVER=self.video_driver,
                   SDL_RENDER_DRIVER='software', SDL_AUDIODRIVER='dummy')
        # The runner anchors config/saves beside $APPIMAGE when it is set.
        env.pop('APPIMAGE', None)
        env.update(self.env_extra)
        args = [str(self.exe), str(self.rom), '--no-launcher', '--port', str(self.port),
                '--max-frames', str(self.max_frames), '--widescreen', self.widescreen,
                '--hash-frames', '60', *self.extra_args]
        if self.fresh:
            args.append('--fresh-evidence')
        args.append('--exec-coverage-out')
        args.append(str(self.out / 'executed-pcs.txt'))
        self._out_file = (self.out / 'stdout.log').open('w')
        self._err_file = (self.out / 'stderr.log').open('w')
        self.proc = subprocess.Popen(args, cwd=self.exe.parent, env=env,
                                     stdout=self._out_file, stderr=self._err_file)
        deadline = time.monotonic() + self.timeout
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError(f'runner exited during startup: {self.proc.returncode}')
            try:
                self.command('ping')
                return
            except (ConnectionRefusedError, ConnectionResetError, OSError):
                if time.monotonic() > deadline:
                    raise TimeoutError('runner TCP server never came up')
                time.sleep(0.05)

    def stop(self, timeout: float = 15.0) -> int | None:
        code = None
        if self.proc is not None:
            if self.proc.poll() is None:
                try:
                    self.command('quit', timeout=2.0)
                except Exception:
                    pass
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                code = self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                code = self.proc.wait(timeout=10)
            self.proc = None
        if self._out_file:
            self._out_file.close()
            self._out_file = None
        if self._err_file:
            self._err_file.close()
            self._err_file = None
        self.copy_manifests()
        return code

    def kill(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        self.proc = None

    def copy_manifests(self):
        for name in ('dispatch_misses.toml', 'floor_coverage.toml',
                     'interior_label_misses.toml', 'floor_unsafe.toml'):
            src = self.exe.parent / name
            if src.exists():
                shutil.copyfile(src, self.out / name)

    # -- TCP -----------------------------------------------------------
    def command(self, cmd: str, timeout: float = 5.0, **args):
        self.request_id += 1
        payload = dict(args, id=self.request_id, cmd=cmd)
        with socket.create_connection(('127.0.0.1', self.port), timeout=timeout) as s:
            s.sendall((json.dumps(payload) + '\n').encode())
            reply = s.makefile().readline()
        self.commands += 1
        response = json.loads(reply)
        if not response.get('ok'):
            raise RuntimeError(f'{cmd}: {response}')
        return response

    def command_many(self, requests):
        """Send several commands in one round trip; returns the parsed replies."""
        self.request_id += 1
        payload = b''
        for cmd, args in requests:
            payload += (json.dumps(dict(args, id=self.request_id, cmd=cmd)) + '\n').encode()
        with socket.create_connection(('127.0.0.1', self.port), timeout=5.0) as s:
            s.sendall(payload)
            reader = s.makefile()
            replies = [json.loads(reader.readline()) for _ in requests]
        self.commands += len(requests)
        for (cmd, _), reply in zip(requests, replies):
            if not reply.get('ok'):
                raise RuntimeError(f'{cmd}: {reply}')
        return replies

    def state_and_frame(self):
        """One round trip: WRAM state block + current frame."""
        block, info = self.command_many([
            ('read_ram', dict(addr='0x%04X' % STATE_LO, size=STATE_LEN)),
            ('frame_info', {}),
        ])
        return RaceState(bytes.fromhex(block['hex']), int(info['current_frame']))

    def step(self, pad: int):
        """Apply `pad` and read the state in ONE round trip.

        The runner services the whole batch in one per-frame poll, which runs
        before that frame's simulation step. So the returned state is the end of
        frame F and the pad is latched for frame F+1: a fixed one-frame control
        delay instead of TCP jitter.
        """
        _, block, info = self.command_many([
            ('set_input', dict(keys='%02X' % pad)),
            ('read_ram', dict(addr='0x%04X' % STATE_LO, size=STATE_LEN)),
            ('frame_info', {}),
        ])
        return RaceState(bytes.fromhex(block['hex']), int(info['current_frame']))

    def frame(self) -> int:
        return int(self.command('frame_info')['current_frame'])

    def wait_frame(self, target: int, timeout: float = 120.0):
        deadline = time.monotonic() + timeout
        while True:
            f = self.frame()
            if f >= target:
                return f
            if time.monotonic() > deadline:
                raise TimeoutError(f'frame {target} not reached (at {f})')
            time.sleep(0.005)

    def ram(self, addr: int, size: int) -> bytes:
        """Read guest WRAM. `addr` is the full 24-bit address or the 16-bit offset."""
        off = addr & 0xFFFF
        return bytes.fromhex(self.command('read_ram', addr=f'0x{off:04X}', size=size)['hex'])

    def ram8(self, addr: int) -> int:
        return self.ram(addr, 1)[0]

    def ram16(self, addr: int) -> int:
        b = self.ram(addr, 2)
        return (b[0] << 8) | b[1]

    def ram32(self, addr: int) -> int:
        b = self.ram(addr, 4)
        return int.from_bytes(b, 'big')

    def vram(self, addr: int, size: int) -> bytes:
        return bytes.fromhex(self.command('read_vram', addr=f'0x{addr:04X}', size=size)['hex'])

    def screenshot(self, path: str | Path):
        path = Path(path)
        if not path.is_absolute():
            path = self.out / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.command('screenshot', path=str(path))
        return path

    def set_input(self, keys: int | str):
        if isinstance(keys, str):
            keys = int(keys, 16)
        self.command('set_input', keys=f'{keys:02X}')

    def press(self, keys: int, frames: int = 6):
        """Hold `keys` for `frames` wall frames, then release."""
        self.set_input(keys)
        target = self.frame() + frames
        self.wait_frame(target)
        self.set_input(0)

    def tap(self, name: str, frames: int = 6):
        self.press(KEYS[name], frames)

    def registers(self) -> dict:
        return self.command('get_registers')

    def dump_ram(self) -> bytes:
        """Full 64 KB WRAM in 4096-byte chunks (the TCP limit per read)."""
        return b''.join(self.ram(off, 0x1000) for off in range(0, 0x10000, 0x1000))

    def dump_ram_file(self, path: str | Path):
        path = Path(path)
        if not path.is_absolute():
            path = self.out / path
        path.write_bytes(self.dump_ram())
        return path


# ---------------------------------------------------------------------------
# Race-state decoding (see docs/RAM_MAP.md). Shared by the driver and the
# route-replay tool so both read exactly the same fields.
# ---------------------------------------------------------------------------
import struct as _struct

P_BASE = 0x18CA
P_POS = P_BASE + 0x00
P_LAT = P_BASE + 0x04
P_VIEW = P_BASE + 0x08
P_SPEED = P_BASE + 0x0E
P_SPEED2 = P_BASE + 0xC2
P_SEG = P_BASE + 0x12
P_CURVE = P_BASE + 0x14
P_SLOPE = P_BASE + 0x16
P_LAP = P_BASE + 0xCA
P_SNAP_STEER = P_BASE + 0x70
P_SNAP_CURVE = P_BASE + 0x86
RACE_PHASE = 0x1866
TWO_P = 0x189E
RACE_CLOCK = 0x23B8
OPPONENT_BASE = 0x053C
OPPONENT_COUNT = 0x217E
LAT_BOUND_LO = 0x1690
LAT_BOUND_HI = 0x1694

STATE_LO = 0x1600
STATE_LEN = 0x0E00    # 0x1600..0x2400 covers bounds, player record and clock


def _dec(kind, b, addr):
    o = addr - STATE_LO
    return _struct.unpack('>' + kind, b[o:o + _struct.calcsize(kind)])[0]


class RaceState:
    """One decoded snapshot from a 0xE00-byte WRAM block read."""

    def __init__(self, block: bytes, frame: int):
        self.frame = frame
        self.clock = _dec('I', block, RACE_CLOCK)
        self.phase = _dec('h', block, RACE_PHASE)
        self.pos = _dec('i', block, P_POS)
        self.lat = _dec('i', block, P_LAT)
        self.view = _dec('i', block, P_VIEW)
        self.speed = _dec('h', block, P_SPEED)
        self.speed2 = _dec('h', block, P_SPEED2)
        self.seg = _dec('h', block, P_SEG)
        self.curv = _dec('h', block, P_CURVE)
        self.slope = _dec('h', block, P_SLOPE)
        self.lap = _dec('h', block, P_LAP)
        self.two_p = _dec('h', block, TWO_P)
        self.lat_lo = _dec('i', block, LAT_BOUND_LO)
        self.lat_hi = _dec('i', block, LAT_BOUND_HI)
        self.opponents = _dec('h', block, OPPONENT_COUNT)
        # Speed-model timers (see $00CF7A / $00CFE0): jump/boost state and
        # countdown timers used by the physics chain.
        self.t34 = _dec('h', block, P_BASE + 0x34)
        self.t36 = _dec('h', block, P_BASE + 0x36)
        self.t38 = _dec('h', block, P_BASE + 0x38)
        self.t2d8 = _dec('h', block, P_BASE + 0x2D8)
        self.t2dc = _dec('b', block, P_BASE + 0x2DC)

    @property
    def lat_units(self) -> float:
        return self.lat / 65536.0

    def dict(self) -> dict:
        return dict(frame=self.frame, clock=self.clock, phase=self.phase,
                    pos=self.pos, lat=self.lat_units, view=self.view,
                    speed=self.speed, speed2=self.speed2, seg=self.seg,
                    curv=self.curv, slope=self.slope, lap=self.lap,
                    two_p=self.two_p, opponents=self.opponents,
                    t34=self.t34, t36=self.t36, t38=self.t38,
                    t2d8=self.t2d8, t2dc=self.t2dc)

    @classmethod
    def read(cls, runner: 'Runner') -> 'RaceState':
        block = runner.ram(STATE_LO, STATE_LEN)
        return cls(block, runner.frame())

