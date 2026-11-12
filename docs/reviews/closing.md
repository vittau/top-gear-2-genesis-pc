# Review closing work

Branch `vittau/review-closing`, based on main `597f287`. No CI or merge.

## Live RACE SOUND row

The runtime setter now updates the native open page's own value word
`$FF2560`, just as its native UP/DOWN handler does. It leaves the global
`$FF240E` sound-mode word to the stock menu teardown and does not touch VRAM.
The existing native row renderer reads the page value normally. The race-policy
freeze guards against treating overlapping race RAM as a menu page. No new
hook/seed, generated-code change, engine patch or per-frame repaint is needed.

Before/after images for the owner to inspect:

| Presentation | Before (incorrect MUSIC) | After (correct SOUND EFFECTS) |
| --- | --- | --- |
| Options off | `build/closing/before/off/live-sfx.png` | `build/closing/e1/off-sound-page/live-sfx.png` |
| Default on | `build/closing/before/on/live-sfx.png` | `build/closing/e1/on-sound-page/live-sfx.png` |

Only fourteen golden leaves were updated, with an explicit allowlist rather
than a full re-record. Both presentations change SOUND-page frame hashes at
1860, 1920, 1980, 2040, 2100 and 2160 (after the live SFX selection), plus their
`live-sfx` PNG SHA-256. Every other field compares exactly to Phase D's golden,
including all ten WAV hashes and all race/live-race pictures.

| Hash | Before | After |
| --- | --- | --- |
| Off page frames 1860..2160 | `658E07DCF7B02CAB` | `F84D070042B7081B` |
| On page frames 1860..2160 | `5DC7B2F499A400FF` | `47EB0D241D51D2DF` |
| Off `live-sfx.png` | `8f5685a654a8805d498dad31b72298839a3c555f9c9a2b142fed35327e361bb4` | `879dc874b0f88d33b65f3d0de1aff330f7dedf485c19249c21429fd4b72c7082` |
| On `live-sfx.png` | `bf9086d7e493a81bcb421b160c9db3775f60ec264df675e2db6fcb89c5798848` | `2dadc58718d858518497dcb71622fc5d50431c2ea9ca6b26bdccee87b3f9c594` |

The additional input-script OPTION sequence covers every directed pair among
SFX/MUSIC/BOTH, including SFX→MUSIC, SFX→BOTH, MUSIC→BOTH and BOTH→SFX. Its
sixteen images (eight changes per presentation) are in
`build/closing/sequences/{off,on}/`. Each PNG equals the canonical page PNG for
the selected value; all manifests are zero. The OPTION directive uses the
same setter as the runtime menu.

Commands/evidence under `build/closing/`:

- Locked `JOBS=3 tools/build-linux.sh`: exit 0, `e1-build.log`.
- Locked `tools/regression.py --out build/closing/e1 --uncapped`: expected exit 1 against the old golden; only the fourteen approved leaves differ (`e1-diff.json`).
- Locked `/opt/homebrew/bin/python3.14 build/closing/e1-sequences.py`: updates only the allowlisted leaves and checks the extra sequences; `e1-sequences.log` and `e1-sequences.json`.
- Locked `/opt/homebrew/bin/python3.14 tools/regression.py --out build/closing/e1-verify --uncapped`: exit 0, all 784 frame, ten WAV and sixteen page hashes match; all manifests zero.

Screenshots/dumps/audio remain under ignored `build/`; only hashes are committed.
