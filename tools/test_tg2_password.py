#!/usr/bin/env python3
"""ROM-grounded password regressions; run: python3 tools/test_tg2_password.py."""
import unittest
from pathlib import Path
import tg2_password as pw

ROM = Path.home() / 'roms/genesis/tg2.bin'


class PasswordTests(unittest.TestCase):
    def test_screen_alphabet_and_legacy_spelling(self):
        self.assertEqual(pw.ALPHABET, 'BCDFGHJKLNPQSTVYZ123456789[]?\\#%')
        self.assertEqual(pw.ALPHABET[14], 'V')
        self.assertEqual(pw.normalise('2UL8 6KP% 6D]] 45P['), '2VL86KP%6D]]45P[')
        with self.assertRaises(ValueError):
            pw.normalise('2OL8 6KP% 6D]] 45P[')

    def test_game_accepted_examples(self):
        germany = pw.decode('2VL8 6KP% 6D]] 45P[')
        self.assertTrue(germany['valid'])
        self.assertEqual((germany['country'], germany['money'], germany['sum']), (5, 100, 151))
        self.assertEqual(germany['_plain'], '2e5064003fffffff0101')
        self.assertEqual(germany['_cipher'], '580e620bfbaf6692876d')
        fresh = pw.encode(u54=1)
        self.assertEqual(pw.spaced(fresh['symbols']), 'KVC2 2HQG CJL2 Y4%T')

    def test_original_country_selector_gate(self):
        germany = '2VL8 6KP% 6D]] 45P['
        self.assertTrue(pw.decode(germany, -1)['valid'])
        self.assertTrue(pw.decode(germany, 5)['valid'])
        self.assertFalse(pw.decode(germany, 11)['valid'])
        self.assertTrue(pw.decode('P%G8 6KP% 6D]] 65P[', 11)['valid'])

    def test_full_checksum_above_255(self):
        record = pw.max_upgrades(5)
        self.assertEqual(record['plain'], '6853ffffffffffffc110')
        self.assertEqual(record['sum'], 2100)
        decoded = pw.decode(record['symbols'])
        self.assertTrue(decoded['valid'])
        self.assertEqual(decoded['_field_sum'], 2100)
        self.assertEqual((decoded['money'], decoded['field30']), (1023, 1023))
        self.assertEqual((decoded['u52'], decoded['u54']), (0, 1))
        for offset in range(0x32, 0x52, 2):
            self.assertEqual(decoded[f'u{offset:x}'], 3)
        # This is what the old 8-bit generator produced: it falsely labelled
        # the truncated-checksum record valid even though the ROM rejects it.
        plain = bytearray.fromhex(record['plain'])
        plain[9] &= 1
        broken = pw.block_to_chars(pw._permute(bytes(plain)))
        self.assertFalse(pw.decode(broken)['valid'])

    def test_legal_range_and_presets(self):
        for money in (127, 128, 255, 256, 1023):
            rec = pw.encode(money=money)
            self.assertTrue(pw.decode(rec['symbols'])['valid'])
        for country in range(16):
            rec = pw.max_upgrades(country, stage=2, two_players=True)
            d = pw.decode(rec['symbols'])
            self.assertTrue(d['valid'])
            self.assertEqual((d['country'], d['stage'], d['flag']), (country, 2, 1))
        for args in ({'money':1024}, {'field30':-1}, {'country':16}, {'u32':4}, {'stage':3}):
            with self.assertRaises(ValueError):
                pw.encode(**args)

    @unittest.skipUnless(ROM.exists(), 'stock USA ROM not present')
    def test_rom_tables_hooks_and_weather(self):
        data = ROM.read_bytes()
        self.assertEqual(data[0x239B2:0x239C2], pw.KEY)
        self.assertEqual(data[0x239C2:0x23A12], bytes(pw.PERM))
        for pc in (0x235C0, 0x235C4):
            self.assertEqual(data[pc:pc+2], bytes.fromhex('4e75'))
        from tg2_weather import races
        rows = races(ROM)
        self.assertEqual({r['index'] for r in rows if r['precipitation']=='rain'}, {3,9,19,20,34,54})
        self.assertEqual({r['index'] for r in rows if r['precipitation']=='snow'}, {23,45,46,59,62})
        self.assertEqual((rows[56]['track'], rows[56]['flags'], rows[56]['precipitation']), ('Geneva','0x44','none'))


if __name__ == '__main__':
    unittest.main()
