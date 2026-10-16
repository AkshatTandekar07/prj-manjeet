"""Tkinter bill and camera preview, without an extra image/UI dependency."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import tkinter as tk
from tkinter import messagebox, ttk

from trolley.client import Client, TrolleyError, money
from trolley.scanner import ScanGate


class App:
    def __init__(self, root, client, camera_index, no_camera=False):
        self.root = root
        self.client = client
        self.gate = ScanGate()
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.ready = False
        self.capture = None
        self.frames = 0
        self.camera_failures = 0
        root.title("Smart Shopping Trolley")
        root.geometry("1040x720")
        root.minsize(820, 620)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Connecting to ESP32…")
        self.total = tk.StringVar(value="Total: —")
        self.action = tk.StringVar(value="add")
        self.barcode = tk.StringVar()
        body = ttk.Frame(root, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Smart Shopping Trolley", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(body, text="Show one barcode. Move it away for 1.5 seconds before scanning it again.").pack(anchor="w", pady=(4, 12))
        self.preview = ttk.Label(body, text="Camera disabled — use manual barcode entry.", anchor="center")
        self.preview.pack()
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=12)
        ttk.Radiobutton(controls, text="Add item", variable=self.action, value="add").pack(side="left")
        ttk.Radiobutton(controls, text="Remove one", variable=self.action, value="remove").pack(side="left", padx=12)
        ttk.Entry(controls, textvariable=self.barcode, width=24).pack(side="left", padx=8)
        ttk.Button(controls, text="Submit barcode", command=self.manual).pack(side="left")
        root.bind("<Return>", lambda event: self.manual())
        ttk.Button(controls, text="Refresh bill", command=lambda: self.submit(self.client.cart)).pack(side="right")
        self.table = ttk.Treeview(body, columns=("name", "price", "quantity", "subtotal"), show="headings", height=6, selectmode="browse")
        for key, title, width in (("name", "Product", 300), ("price", "Unit price", 140), ("quantity", "Quantity", 90), ("subtotal", "Subtotal", 140)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="w" if key == "name" else "e")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=12)
        ttk.Label(bottom, textvariable=self.total, font=("Segoe UI", 20, "bold")).pack(side="left")
        ttk.Button(bottom, text="Clear cart…", command=self.clear).pack(side="right")
        ttk.Button(bottom, text="Remove selected", command=self.remove_selected).pack(side="right", padx=8)
        ttk.Label(body, textvariable=self.status, wraplength=950).pack(anchor="w")
        if not no_camera:
            self.open_camera(camera_index)
        self.submit(self.client.cart)
        root.after(40, self.tick)

    def open_camera(self, index):
        try:
            import cv2
            from pyzbar.pyzbar import decode, ZBarSymbol

            self.cv2 = cv2
            self.decode = decode
            self.symbols = [ZBarSymbol.EAN13, ZBarSymbol.EAN8, ZBarSymbol.UPCA, ZBarSymbol.UPCE, ZBarSymbol.CODE128]
            self.capture = cv2.VideoCapture(index)
            if not self.capture.isOpened():
                self.capture.release()
                self.capture = None
                raise RuntimeError("Camera unavailable. Check Windows camera permission or camera_index in config.json.")
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        except (ImportError, OSError, RuntimeError) as exc:
            messagebox.showwarning("Camera unavailable", f"{exc}\n\nManual barcode entry is still available.")

    def submit(self, task):
        if self.pending is not None:
            self.status.set("Please wait for the current request.")
            return
        self.status.set("Contacting ESP32…")
        self.pending = self.worker.submit(task)

    def scan(self, barcode):
        if not self.ready or self.pending is not None:
            self.status.set("Refresh the bill and wait for connection before scanning.")
            return
        action = self.action.get()
        self.submit(lambda: self.client.scan(barcode, action))

    def manual(self):
        barcode = self.barcode.get().strip()
        if barcode:
            self.scan(barcode)

    def remove_selected(self):
        selected = self.table.selection()
        if selected and self.ready:
            self.submit(lambda: self.client.scan(selected[0], "remove"))

    def clear(self):
        if self.ready and self.pending is None and messagebox.askyesno("Clear trolley", "Remove every item from the trolley bill?"):
            self.submit(self.client.clear)

    def render_cart(self, cart):
        self.table.delete(*self.table.get_children())
        for item in cart["items"]:
            self.table.insert("", "end", iid=item["barcode"], values=(item["name"], money(item["price_paise"]), item["quantity"], money(item["price_paise"] * item["quantity"])))
        self.total.set(f"Total: {money(cart['total_paise'])}")

    def tick(self):
        if self.pending is not None and self.pending.done():
            try:
                self.render_cart(self.pending.result())
                self.ready = True
                self.status.set("Connected. Ready to scan.")
            except Exception as exc:
                self.ready = False
                self.status.set(f"{exc} Click Refresh bill to reconnect. Displayed bill may be stale.")
            self.pending = None
        if self.capture is not None:
            ok, frame = self.capture.read()
            if ok:
                self.camera_failures = 0
                self.frames += 1
                if self.frames % 3 == 0:
                    gray = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
                    codes = []
                    for found in self.decode(gray, symbols=self.symbols):
                        try:
                            code = found.data.decode("ascii")
                        except UnicodeDecodeError:
                            continue
                        if code.isdigit() and code not in codes:
                            codes.append(code)
                    fresh = self.gate.observe(codes, time.monotonic())
                    if fresh and self.ready and self.pending is None:
                        self.scan(fresh)
                frame = self.cv2.resize(frame, (640, 300))
                encoded_ok, encoded = self.cv2.imencode(".ppm", frame)
                if encoded_ok:
                    self.photo = tk.PhotoImage(data=encoded.tobytes(), format="PPM")
                    self.preview.configure(image=self.photo, text="")
            else:
                self.camera_failures += 1
                if self.camera_failures >= 30:
                    self.capture.release()
                    self.capture = None
                    self.preview.configure(image="", text="Camera disconnected. Use manual entry or restart the app.")
        self.root.after(40, self.tick)

    def close(self):
        if self.capture is not None:
            self.capture.release()
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Laptop scanner for the ESP32 shopping trolley")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--no-camera", action="store_true", help="Use manual entry without opening the camera")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig"))
        client = Client(config["esp32_url"], config["api_token"])
        index = config.get("camera_index", 0)
        if type(index) is not int or index < 0:
            raise ValueError("camera_index must be a nonnegative integer")
    except (OSError, ValueError, KeyError, TypeError, TrolleyError) as exc:
        parser.exit(1, f"Configuration error: {exc}\nCopy config.example.json to config.json and enter your ESP32 address and token.\n")
    root = tk.Tk()
    App(root, client, index, args.no_camera)
    root.mainloop()
