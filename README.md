# Smart Shopping Trolley

A Windows laptop reads product barcodes using its camera. An ESP32 looks up products, owns the cart, and calculates the bill. No internet is required after installation; both devices need a local Wi-Fi connection.

The laptop app provides a camera preview, itemized bill, quantities, add/remove mode, manual barcode entry, refresh, and confirmed cart clearing. Prices use integer paise. The ESP32 remembers recent request IDs to avoid duplicate charges when the laptop retries a lost response.

## Installed locally

- Python packages in `.venv`: OpenCV, pyzbar, and NumPy (OpenCV's dependency).
- Arduino CLI 1.5.1, ESP32 Arduino core 3.3.12, compilers, and supporting tools in `.tools`.
- Python 3.12 is selected using uv; an existing uv-managed installation is reused.
- Tkinter, HTTP, JSON, threading, and tests use Python's standard library.

Windows ZBar DLLs ship with the pyzbar wheel. If DLL loading fails on another laptop, see the [pyzbar Windows requirements](https://pypi.org/project/pyzbar/). ESP32 installation follows [Espressif's board package](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html).

To reproduce the local setup from PowerShell in this directory:

```powershell
.\scripts\setup.ps1
uv run python -m unittest discover -s tests -v
```

If your PowerShell policy blocks local scripts, use `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1` for this invocation. Arduino CLI downloads are verified against the official release checksum; the board manager verifies its package downloads.

## Configure and upload the ESP32

The default board target is the classic **ESP32-WROOM / ESP32 Dev Module**, not an ESP32-C3, S3, or other variant. Connect it with a USB **data** cable.

1. Open `firmware/trolley/secrets.h` (setup creates it from `secrets.example.h`). Enter your Wi-Fi name and password. Classic ESP32 uses a **2.4 GHz** network.
2. Use the same random alphanumeric API token in `secrets.h` and `config.json`. Setup generates a matching token for you. These files are ignored by Git. Do not share them.
3. Edit `PRODUCTS` in `firmware/trolley/Cart.h` with real barcode strings, product names, and prices in **paise**. For example, INR 30.00 is `3000`. Keep leading zeros in barcode strings. Recompile and upload after changing products or credentials.
4. Find the port and upload:

```powershell
.\scripts\arduino.ps1 -Action Ports
.\scripts\arduino.ps1 -Action Upload -Port COM3
.\scripts\arduino.ps1 -Action Monitor -Port COM3
```

Replace `COM3` with your board's actual port. If needed, hold BOOT while the uploader connects. A board that does not appear may need its manufacturer's CP210x or CH340 USB driver. No driver is installed automatically because the board model is not known.

At boot, the ESP32 runs a billing self-check and prints its address, for example `http://192.168.1.100`, at 115200 baud. Set `esp32_url` in `config.json` to that address. Close the monitor before another upload.

Compile without uploading:

```powershell
.\scripts\arduino.ps1 -Action Compile
```

Without `secrets.h`, compilation uses the example header; the firmware refuses to connect until credentials are configured. For another board, pass its FQBN using `-Board`, for example `-Board esp32:esp32:esp32s3`, after confirming your exact model.

## Run the scanner

```powershell
uv run python -m trolley
```

Allow desktop camera access in Windows privacy settings. If necessary, change `camera_index` from `0` to `1` in `config.json` for an external camera. To use only manual entry:

```powershell
uv run python -m trolley --no-camera
```

Wait for **Connected. Ready to scan.** Hold one well-lit barcode close enough to fill a useful portion of the camera preview. Supported symbologies are EAN-13, EAN-8, UPC-A, UPC-E, and numeric Code 128. Store the decoder's exact digit string in the product table; some UPC labels may be decoded as EAN-13 with a leading zero.

A held barcode counts once. Move it completely out of view for at least 1.5 seconds, then present it again for another unit. Multiple different barcodes in one frame are ignored. In **Remove one** mode a scan removes one unit. You can also select a bill row and click **Remove selected**.

Unknown products do not change the bill. After any request error, refresh the bill before continuing. If a connection fails after submission, the operation may already have reached the ESP32: read the refreshed quantity before submitting another scan.

### Sample products

These are demonstration assignments, not a real retail product database:

| Barcode | Product | Price |
| --- | --- | --- |
| `4006381333931` | Milk 500 ml | INR 30.00 |
| `5901234123457` | Bread | INR 45.00 |
| `12345670` | Biscuits | INR 20.00 |
| `012345678905` | Rice 1 kg | INR 65.00 |

Use manual entry to try these after connecting the ESP32. `docs/sample-barcode.png` is a printable test image for the milk sample. No ESP32 emulator is included; Python tests use a local HTTP fixture to check the client protocol.

## Device API

All endpoints require the `X-API-Key` header. Responses contain `session`, `items`, and `total_paise`; each item contains `barcode`, `name`, `price_paise`, and `quantity`. Errors contain an `error` message.

| Method | Path | URL-encoded form body |
| --- | --- | --- |
| GET | `/api/cart` | None |
| POST | `/api/scan` | `barcode`, `action=add` or `remove`, `request_id`, `session` |
| POST | `/api/clear` | `request_id`, `session` |

Read the cart first to get the boot session. Each mutation needs a new 32-character hexadecimal request ID. Retries must reuse that ID and payload. The last 32 successful IDs are retained; replay returns the current bill without applying the operation again. An ESP32 restart changes the session and rejects old mutations. Maximum quantity is 999 per product; bills cannot exceed a 32-bit unsigned paise amount.

## Scope and limits

- The cart and product table live on the ESP32; **the cart resets on reboot or loss of power**. There is no payment processing, tax calculation, or checkout persistence.
- Use one laptop client per trolley. Refresh reads the current bill; it does not poll other clients automatically.
- This is a local-network prototype using HTTP and a shared token. Use a trusted Wi-Fi network; do not forward the ESP32's port to the internet. HTTP does not encrypt the token or bill.
- A phone hotspot must allow devices to communicate with each other. Guest-network isolation may block requests even when both devices are connected.
- Optional LCD support is deferred until the LCD model, I2C backpack voltage, and wiring are known. Do not connect a 5 V I2C pull-up directly to ESP32 GPIOs.
- Tests cover real image decoding, scan suppression, HTTP request formatting/retries, validation, and the laptop UI. Firmware billing self-checks run on the board at boot; camera focus, Wi-Fi, USB upload, and physical device behavior still require hardware checks.
