"""A barcode must leave view before it can be counted again."""


class ScanGate:
    def __init__(self, absence_seconds=1.5):
        self.absence_seconds = absence_seconds
        self.last_seen = {}

    def observe(self, barcodes, now):
        self.last_seen = {
            code: seen for code, seen in self.last_seen.items()
            if code in barcodes or now - seen < self.absence_seconds
        }
        fresh = [code for code in barcodes if code not in self.last_seen]
        for code in barcodes:
            self.last_seen[code] = now
        # Ambiguous frames never add multiple products by accident.
        return fresh[0] if len(barcodes) == 1 and fresh else None
