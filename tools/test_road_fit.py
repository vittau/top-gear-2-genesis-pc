#!/usr/bin/env python3
"""Numeric qualification of the real C road fitter (requires NumPy and cc).

Run under the heavy lock. Builds a temporary shared library under build/;
checks the box constraints and convex optimum, including missing stripe rows.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT / 'build'
    directory.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='road-fit-', dir=directory) as tmp:
        library = Path(tmp) / ('fit.dylib' if sys.platform == 'darwin' else 'fit.so')
        subprocess.run([os.environ.get('CC', 'cc'), '-shared', '-fPIC', '-O2',
                        str(ROOT / 'game/tg2_road_fit.c'), '-o', str(library), '-lm'], check=True)
        dll = ctypes.CDLL(str(library))
        fit = dll.tg2_road_fit
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
        bytes_ = np.ctypeslib.ndpointer(dtype=np.uint8, flags='C_CONTIGUOUS')
        fit.argtypes = [doubles, bytes_, ctypes.c_int, doubles]
        fit.restype = None
        rng = np.random.default_rng(219)
        cases = 0
        max_kkt = 0.0
        for n in (1, 2, 3, 5, 12, 32, 80, 160, 224):
            x = np.arange(n, dtype=float)
            for kind in range(18):
                target = 100 + .7*x
                if kind >= 2:
                    target += 20*np.sin(x/17) + .008*x*x
                raw = np.ascontiguousarray(target if kind == 0 else
                    np.round(target + rng.uniform(-2, 2, n)))
                if kind >= 12:
                    raw = np.ascontiguousarray(100 + rng.normal(0, 20, n))
                observed = np.ones(n, dtype=np.uint8)
                if kind >= 6 and n > 2:
                    observed[1:-1] = rng.random(n-2) > .65
                out = np.empty(n)
                fit(raw, observed, n, out)
                assert np.isfinite(out).all()
                assert np.max(np.abs(out[observed != 0]-raw[observed != 0])) <= 2+1e-8
                if n < 3:
                    assert np.array_equal(out, raw)
                else:
                    # KKT conditions independently certify the global optimum
                    # of this strictly convex banded problem, not just a
                    # lower error than the authored staircase.
                    d2 = np.diff(out, n=2)
                    gradient = observed*(out-raw)
                    gradient[:-2] += 64*d2
                    gradient[1:-1] -= 128*d2
                    gradient[2:] += 64*d2
                    lower = (observed != 0) & (out-raw < -2+1e-7)
                    upper = (observed != 0) & (out-raw > 2-1e-7)
                    free = ~(lower | upper)
                    error = max(np.abs(gradient[free]).max(initial=0),
                                (-gradient[lower]).max(initial=0),
                                gradient[upper].max(initial=0))
                    max_kkt = max(max_kkt, float(error))
                    assert error < 1e-5, (n, kind, error)
                    if kind == 0:
                        assert np.max(np.abs(out-target)) < 1e-8
                # Translation and left/right reflection must commute with fit.
                mirrored = np.empty(n)
                fit(np.ascontiguousarray(512-raw), observed, n, mirrored)
                assert np.max(np.abs(mirrored-(512-out))) < 1e-7
                cases += 1
        print(f'{cases} fits + reflections pass; worst KKT residual {max_kkt:.3g}')


if __name__ == '__main__':
    main()
