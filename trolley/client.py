"""Small HTTP client; all product lookup and billing happen on the ESP32."""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4


class TrolleyError(Exception):
    pass


def validate_barcode(barcode):
    if not isinstance(barcode, str) or not 1 <= len(barcode) <= 32 or not barcode.isascii() or not barcode.isdigit():
        raise TrolleyError("Use a barcode containing 1–32 digits.")
    return barcode


def money(paise):
    return f"INR {paise // 100}.{paise % 100:02d}"


class Client:
    def __init__(self, base_url, token, timeout=2):
        parts = urlsplit(base_url)
        if parts.scheme != "http" or not parts.hostname or parts.username or parts.password or parts.path not in ("", "/") or parts.query or parts.fragment:
            raise TrolleyError("esp32_url must look like http://192.168.1.100")
        if not isinstance(token, str) or not 16 <= len(token) <= 128 or not token.isascii() or not token.isalnum():
            raise TrolleyError("Use the same 16–128 character alphanumeric API token on both devices.")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = None
        # Device traffic must stay direct, even when Windows has a proxy configured.
        self.http = build_opener(ProxyHandler({}))

    def _request(self, path, fields=None):
        request = Request(
            self.base_url + path,
            data=None if fields is None else urlencode(fields).encode("ascii"),
            headers={"X-API-Key": self.token, "Content-Type": "application/x-www-form-urlencoded"},
        )
        for attempt in range(2):
            try:
                with self.http.open(request, timeout=self.timeout) as response:
                    data = json.loads(response.read(65537))
                self._validate_cart(data)
                self.session = data["session"]
                return data
            except HTTPError as exc:
                try:
                    message = json.loads(exc.read(4096)).get("error", f"HTTP {exc.code}")
                except (ValueError, AttributeError):
                    message = f"HTTP {exc.code}"
                finally:
                    exc.close()
                raise TrolleyError(str(message)) from None
            except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
                if attempt:
                    raise TrolleyError("Connection lost. The result may be unknown; refresh the bill before scanning again.") from exc
            except (ValueError, KeyError, TypeError, TrolleyError) as exc:
                raise TrolleyError("Invalid ESP32 response; refresh the bill before scanning again.") from exc

    @staticmethod
    def _validate_cart(data):
        if not isinstance(data, dict) or not isinstance(data.get("session"), str) or not data["session"]:
            raise ValueError("Missing session")
        if not isinstance(data.get("items"), list) or len(data["items"]) > 100:
            raise ValueError("Invalid items")
        total = 0
        seen = set()
        for item in data["items"]:
            barcode = item["barcode"]
            validate_barcode(barcode)
            if barcode in seen or not isinstance(item["name"], str):
                raise ValueError("Invalid product")
            seen.add(barcode)
            if type(item["quantity"]) is not int or not 1 <= item["quantity"] <= 999:
                raise ValueError("Invalid quantity")
            if type(item["price_paise"]) is not int or item["price_paise"] < 0:
                raise ValueError("Invalid price")
            total += item["quantity"] * item["price_paise"]
        if type(data.get("total_paise")) is not int or data["total_paise"] != total:
            raise ValueError("Invalid total")

    def cart(self):
        return self._request("/api/cart")

    def _change(self, path, **fields):
        if self.session is None:
            self.cart()
        return self._request(path, {**fields, "request_id": uuid4().hex, "session": self.session})

    def scan(self, barcode, action="add"):
        validate_barcode(barcode)
        if action not in ("add", "remove"):
            raise TrolleyError("Action must be add or remove.")
        return self._change("/api/scan", barcode=barcode, action=action)

    def clear(self):
        return self._change("/api/clear")
