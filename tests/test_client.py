from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs

from trolley.client import Client, TrolleyError, money, validate_barcode


TOKEN = "0123456789abcdef0123456789abcdef"
EMPTY = {"session": "boot-1", "items": [], "total_paise": 0}
MILK = {"barcode": "4006381333931", "name": "Milk 500 ml", "price_paise": 3000, "quantity": 2}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        fields = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        self.server.requests.append((self.command, self.path, self.headers.get("X-API-Key"), fields))
        response = deepcopy(EMPTY)
        status = 200
        if self.headers.get("X-API-Key") != TOKEN:
            status, response = 401, {"error": "Invalid API token."}
        elif self.path == "/api/scan":
            if fields.get("barcode") == ["99999999"]:
                status, response = 422, {"error": "Unknown barcode."}
            elif fields.get("session") != ["boot-1"]:
                status, response = 409, {"error": "ESP32 restarted. Refresh the bill."}
            else:
                response["items"] = [MILK]
                response["total_paise"] = 6000
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    do_GET = handle_request
    do_POST = handle_request


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.requests = []
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}", TOKEN)

    def test_cart_scan_remove_clear_protocol(self):
        self.assertEqual(self.client.cart(), EMPTY)
        self.assertEqual(self.client.scan(MILK["barcode"])["total_paise"], 6000)
        self.client.scan(MILK["barcode"], "remove")
        self.client.clear()
        requests = self.server.requests
        self.assertEqual([r[1] for r in requests], ["/api/cart", "/api/scan", "/api/scan", "/api/clear"])
        self.assertTrue(all(r[2] == TOKEN for r in requests))
        self.assertEqual(requests[2][3]["action"], ["remove"])
        ids = [r[3]["request_id"][0] for r in requests[1:]]
        self.assertEqual(len(set(ids)), 3)
        self.assertTrue(all(len(value) == 32 for value in ids))
        self.assertTrue(all(r[3]["session"] == ["boot-1"] for r in requests[1:]))

    def test_unknown_product_and_wrong_token_are_reported(self):
        with self.assertRaisesRegex(TrolleyError, "Unknown barcode"):
            self.client.scan("99999999")
        self.client.token = "f" * 32
        with self.assertRaisesRegex(TrolleyError, "Invalid API token"):
            self.client.cart()

    def test_session_is_fetched_before_first_mutation_and_reboot_is_rejected(self):
        self.client.scan(MILK["barcode"])
        self.assertEqual(self.server.requests[0][0], "GET")
        self.client.session = "previous-boot"
        with self.assertRaisesRegex(TrolleyError, "restarted"):
            self.client.scan(MILK["barcode"])

    def test_transport_retry_reuses_identical_request_id(self):
        self.client.session = "boot-1"
        original = self.client.http.open
        attempts = []

        def flaky(request, **kwargs):
            attempts.append(request.data)
            if len(attempts) == 1:
                raise URLError("Response lost")
            return original(request, **kwargs)

        with patch.object(self.client.http, "open", side_effect=flaky):
            self.client.scan(MILK["barcode"])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])

    def test_offline_request_stops_after_two_attempts(self):
        with patch.object(self.client.http, "open", side_effect=URLError("offline")) as opened:
            with self.assertRaisesRegex(TrolleyError, "result may be unknown"):
                self.client.cart()
            self.assertEqual(opened.call_count, 2)

    def test_validate_response_rejects_wrong_totals_and_quantities(self):
        cart = {"session": "boot-1", "items": [deepcopy(MILK)], "total_paise": 6000}
        Client._validate_cart(cart)
        for quantity, total in ((0, 0), (-1, -3000), (True, 3000), (1000, 3000000), (2, 5999)):
            cart["items"][0]["quantity"] = quantity
            cart["total_paise"] = total
            with self.assertRaises(ValueError):
                Client._validate_cart(cart)

    def test_leading_zeros_and_integer_money(self):
        self.assertEqual(validate_barcode("012345678905"), "012345678905")
        self.assertEqual(money(3005), "INR 30.05")
        for barcode in ("", "١٢٣", "12a", "1" * 33, 123):
            with self.assertRaises(TrolleyError):
                validate_barcode(barcode)
        for address in ("https://example.com", "http://user:pass@localhost", "http://localhost/api", "http://localhost?token=123"):
            with self.assertRaises(TrolleyError):
                Client(address, TOKEN)
