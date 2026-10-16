import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from trolley.app import App, main
from trolley.client import TrolleyError


class AppTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.client = Mock()
        self.client.cart.return_value = {
            "session": "test",
            "items": [{"barcode": "4006381333931", "name": "Milk", "quantity": 2, "price_paise": 3000}],
            "total_paise": 6000,
        }
        self.app = App(self.root, self.client, 0, no_camera=True)
        self.finish_request()

    def tearDown(self):
        self.app.close()

    def finish_request(self):
        try:
            self.app.pending.result(timeout=2)
        except TrolleyError:
            pass
        self.app.tick()

    def test_renders_bill_and_submits_manual_add_remove(self):
        self.assertTrue(self.app.ready)
        self.assertEqual(self.app.total.get(), "Total: INR 60.00")
        self.assertEqual(self.app.table.item("4006381333931", "values"), ("Milk", "INR 30.00", "2", "INR 60.00"))
        self.client.scan.return_value = self.client.cart.return_value
        self.app.barcode.set("4006381333931")
        self.app.manual()
        self.finish_request()
        self.client.scan.assert_called_with("4006381333931", "add")
        self.app.table.selection_set("4006381333931")
        self.app.remove_selected()
        self.finish_request()
        self.client.scan.assert_called_with("4006381333931", "remove")

    def test_error_marks_bill_stale_and_clear_requires_confirmation(self):
        with patch("trolley.app.messagebox.askyesno", return_value=False):
            self.app.clear()
        self.client.clear.assert_not_called()
        self.client.cart.side_effect = TrolleyError("offline")
        self.app.submit(self.client.cart)
        self.finish_request()
        self.assertFalse(self.app.ready)
        self.assertIn("stale", self.app.status.get())


class ConfigTests(unittest.TestCase):
    def test_windows_powershell_utf8_bom_config(self):
        with TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"esp32_url": "http://192.168.1.100", "api_token": "a" * 32}), encoding="utf-8-sig")
            with patch("sys.argv", ["trolley", "--config", str(config), "--no-camera"]), patch("trolley.app.tk.Tk") as root, patch("trolley.app.App") as app:
                main()
                self.assertTrue(app.call_args.args[3])
                root.return_value.mainloop.assert_called_once()
