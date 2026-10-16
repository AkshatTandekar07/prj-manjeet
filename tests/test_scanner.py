import unittest

import cv2
import numpy as np
from pyzbar.pyzbar import decode

from trolley.scanner import ScanGate


def ean13_image(code):
    """Generate a clean test barcode, including quiet zones, without another package."""
    left = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
    even = ("0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111")
    parity = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")
    assert len(code) == 13 and code.isascii() and code.isdigit()
    assert sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(code)) % 10 == 0
    bits = "0" * 12 + "101"
    for digit, kind in zip(code[1:7], parity[int(code[0])]):
        bits += (left if kind == "L" else even)[int(digit)]
    bits += "01010"
    for digit in code[7:]:
        bits += "".join("1" if bit == "0" else "0" for bit in left[int(digit)])
    bits += "101" + "0" * 12
    row = np.array([0 if bit == "1" else 255 for bit in bits], dtype=np.uint8)
    return np.tile(np.repeat(row, 4), (200, 1))


class ScannerTests(unittest.TestCase):
    def test_held_barcode_is_counted_once(self):
        gate = ScanGate()
        self.assertEqual(gate.observe(["123"], 0), "123")
        for now in (0.2, 1.8, 5):
            self.assertIsNone(gate.observe(["123"], now))

    def test_brief_decoder_dropout_does_not_count_again(self):
        gate = ScanGate()
        gate.observe(["123"], 0)
        gate.observe([], 0.1)
        self.assertIsNone(gate.observe(["123"], 0.5))
        gate.observe([], 0.8)
        gate.observe([], 2.1)
        self.assertEqual(gate.observe(["123"], 2.2), "123")

    def test_different_barcode_can_be_scanned_immediately(self):
        gate = ScanGate()
        gate.observe(["123"], 0)
        self.assertEqual(gate.observe(["456"], 0.1), "456")

    def test_multiple_barcodes_are_not_counted(self):
        gate = ScanGate()
        self.assertIsNone(gate.observe(["123", "456"], 0))
        self.assertIsNone(gate.observe(["123"], 0.1))

    def test_real_zbar_decoder_reads_generated_sample(self):
        image = ean13_image("4006381333931")
        self.assertEqual([found.data for found in decode(image)], [b"4006381333931"])
        ok, encoded = cv2.imencode(".png", image)
        self.assertTrue(ok)
        round_trip = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        self.assertEqual(decode(round_trip)[0].data, b"4006381333931")
