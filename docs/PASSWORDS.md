# Top Gear 2 (Genesis) passwords — reversed from the stock ROM

The main menu's **CONTINUE → PASSWORDS** row opens the game's own
**ENTER PASSWORD** screen. That screen is the cleanest way to reach any of the
16 tracks: the password encodes the championship country (that is, the track),
the stage, the money and the car upgrades, and the game loads it with no
emulator help.

Everything below was recovered from the raw ROM and then confirmed against the
running game (see *Verification*).

| ROM address | Role |
|---|---|
| `$023594` | validator: any empty symbol → invalid; decode; checksum; stage/country range checks |
| `$02396A` | 16 symbols → 80-bit block (salt subtraction + bit packing) |
| `$02392A` | 80-bit block → 16 symbols (the game's own display encoder) |
| `$0238D2` | 80-bit block → 10-byte plaintext record (bit permutation) |
| `$023884` | inverse of `$0238D2` |
| `$02371A` | 10-byte record → per-field words at `$26..$54(a0)` |
| `$0235C6` | per-field words → 10-byte record |
| `$0239B2` | 16-byte salt key `"gnarreKdaehrotoM"` |
| `$0239C2` | 80-byte bit permutation table |

The work area is the 0x60-byte struct at **`$FF2570`**:

| Offset | Meaning |
|---|---|
| `+$00..$0F` | the 16 entered symbols (codes 1..32) |
| `+$10..$19` | packed 80-bit block after the salt step |
| `+$1A..$23` | un-permuted 10-byte plaintext record |
| `+$24` | word: index the screen demands (country picker index, `-1` from the PASSWORD row) |
| `+$26..$54` | decoded fields (see below) |

## Symbols

The on-screen keyboard is a 13-column grid. The 32 password symbols appear in
this exact order; values 27..32 are the punctuation keys and the arrows,
`DEL` and `END` are control keys.

```
row 0:  B C D F G H J K L N P Q S            codes  1..13
row 1:  T U Y Z 1 2 3 4 5 6 7 8 9            codes 14..26
row 2:  [ ] ? \ # %  LEFT RIGHT  DEL  END    codes 27..32, END = col 12
```

`ALPHABET = "BCDFGHJKLNPQSTUYZ123456789[]?\\#%"` (32 symbols; no `A`, `E`, `M`,
`O`, `R`, `V`, `W`, `X`). `A` inserts the symbol under the cursor, `END`
submits.

## Encoding pipeline

1. **Salt.** With `KEY = "gnarreKdaehrotoM"` and `code[i]` the 1-based symbol
   code, each symbol yields a 5-bit value
   `v[i] = (code[i] - 1 - KEY[i]) & 0x1F`.
2. **Pack.** The 16 values concatenate big-endian: symbol 0 occupies bits
   75..79 of an 80-bit block, symbol 15 bits 0..4.
   `block = Σ v[i] << (5 * (15 - i))`.
3. **Un-permute.** `plain[i] = block[PERM[i]]`, where `PERM` is the 80-entry
   table at `$0239C2` and bits are numbered most-significant-first inside the
   10-byte buffers (`bit n` = byte `n/8`, bit `7 - n%8`).
4. **Unpack fields.** The plaintext record holds the fields below.

The game runs the same steps in reverse to print a password
(`$0235C6` → `$023884` → `$02392A`); that is how it prefills the screen.

## Record layout

Bit offsets are into the plaintext record, MSB first.

| Field | Offset | Width | Meaning |
|---|---:|---:|---|
| `sum` | 0..6 (byte 0 bits 7..1) + 79 (byte 9 bit 0) | 8 | additive checksum |
| `flag` | 7 | 1 | always 0 in every password seen |
| `country` | 8 | 4 | **track/country index 0..15** |
| `stage` | 12 | 2 | checked `<= 2` by the validator |
| `money` | 14 | 10 | money in thousands of dollars ($255,000 shows as `$255000`) |
| `field30` | 24 | 10 | not exercised; 0 in all observed passwords |
| `u32 .. u4e` | 34..63 | 2 each (15 fields) | per-part/upgrade state, 0..3 |
| `u50` | 64 | 2 | |
| `u52` | 66 | 3 | |
| `u54` | 69 | 3 | 1 in the stock fresh-game password |

Bits 72..78 of the record are unused (7 don't-care bits).

**Checksum.** `sum = (Σ every other field) & 0xFF`. The ROM compares the sum
as a **16-bit word** (`cmp.w $26(a0),d7` at `$0235A4`), so a password whose
fields add up to more than 255 is rejected even though only 8 bits are stored.
That is why money and upgrades trade off against each other: e.g. money 255
plus one level-3 upgrade (sum 258) is invalid, while money 100 plus every
upgrade (sum 162) is fine.

**Validation rules** (`$023594`):
* any zero symbol → invalid;
* checksum mismatch → invalid;
* `stage > 2` → invalid;
* the selected picker index (`+$24`) must be `<= country`; the PASSWORD row
  passes `-1`, so a password entered there can name any country.

## Countries / tracks

`country` 0..15 selects the championship country, and the country picker lists
them in the same order:

| Value | Country | Track (from the intro panel) |
|---:|---|---|
| 0 | Australasia | Auckland |
| 1 | Britain | Loch Ness |
| 2 | Canada | (see `build/qual/cov/c02-*/intro-*.png`) |
| 3..15 | — | see the per-run `intro-*.png` in the coverage ledger |

The prefilled password on a fresh boot —
`KUC2 2HQG CJL2 Y4%T` — decodes to country 0, money 0, `u54 = 1`, checksum 1,
i.e. exactly the fresh-game state, and the game accepts it.

## Generator

`tools/tg2_password.py` implements encode/decode:

```sh
python3 tools/tg2_password.py decode "KUC2 2HQG CJL2 Y4%T"
python3 tools/tg2_password.py encode --field country=5 --field money=100
```

`tools/tg2_password_ui.py` types a generated password through the ENTER
PASSWORD screen, verifying every inserted symbol against `$FF2570`;
`tools/tg2_coverage.py` builds on it to load a track and drive it.

## Verification

* The ROM's own prefilled password decodes with a matching checksum
  (`tools/tg2_password.py decode`), and pressing `END` on it is accepted by the
  game (it returns to the game-setup screen, not "INVALID PASSWORD").
* The generated `country=1` password (`KUF2 2HQG CJL2 Y4YT`) is accepted and
  the next intro panel reads **Britain / Loch Ness**; `country=0` gives
  **Australasia / Auckland**. Every one of the 16 values loads a different
  track — see `docs/VALIDATION.md` section 2.
* A password whose fields sum past 255 is rejected, matching the 16-bit
  checksum comparison.
* Runtime cross-check: with a breakpoint on `$023594`, `A0 = $FF2570`, and the
  struct contains the entered symbols, the packed block, the plaintext and the
  decoded fields exactly as this document describes.
