#!/usr/bin/env python3
"""ROM-free regression: rows stay fresh beyond the old 16-bit serial limit."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
#include <assert.h>
#include "app_config.h"
#include "video/genesis_vdp.h"
#include "tg2_highres.h"
AppConfig g_app_config;
static GVDP vdp;
int main(void) {
    g_app_config.internal_scale = 2;
    tg2_highres_reset();
    for (unsigned picture = 1; picture <= 131074; ++picture) {
        tg2_highres_picture_start();
        assert(tg2_highres_serial() == picture);
        /* A row not captured this picture must not look fresh. */
        assert(tg2_highres_row_serial()[100] != tg2_highres_serial());
        tg2_highres_capture_row(&vdp, 100, 0, 0);
        assert(tg2_highres_row_serial()[100] == tg2_highres_serial());
    }
    tg2_highres_reset();
    assert(tg2_highres_serial() == 0);
    assert(tg2_highres_row_serial()[100] == 0);
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='tg2-serial-') as temp:
    path = Path(temp)
    (path / 'serial.c').write_text(SOURCE)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-O1',
                    '-I' + str(ROOT / 'game'),
                    '-I' + str(ROOT / 'segagenesisrecomp/runner'),
                    str(path / 'serial.c'), str(ROOT / 'game/tg2_highres.c'),
                    '-lm', '-o', str(path / 'serial')], check=True)
    env = dict(os.environ)
    env.pop('TG2_HIGHRES_SCALE', None)
    subprocess.run([str(path / 'serial')], env=env, check=True)
print('PASS: 131074 pictures retain fresh/stale row identity, then reset')
