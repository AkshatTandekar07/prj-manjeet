#pragma once
#include <stdint.h>
#include <string.h>

struct Product {
  const char* barcode;
  const char* name;
  uint32_t pricePaise;
};

// Demonstration barcodes and prices; replace with the labels on your products.
constexpr Product PRODUCTS[] = {
  {"4006381333931", "Milk 500 ml", 3000},
  {"5901234123457", "Bread", 4500},
  {"12345670", "Biscuits", 2000},
  {"012345678905", "Rice 1 kg", 6500},
};
constexpr unsigned PRODUCT_COUNT = sizeof(PRODUCTS) / sizeof(PRODUCTS[0]);

class Cart {
public:
  uint16_t quantities[PRODUCT_COUNT] = {};

  int find(const char* barcode) const {
    for (unsigned i = 0; i < PRODUCT_COUNT; ++i) {
      if (strcmp(PRODUCTS[i].barcode, barcode) == 0) return i;
    }
    return -1;
  }

  uint32_t total() const {
    uint64_t result = 0;
    for (unsigned i = 0; i < PRODUCT_COUNT; ++i) {
      result += uint64_t(PRODUCTS[i].pricePaise) * quantities[i];
    }
    return uint32_t(result);
  }

  const char* change(const char* barcode, bool remove) {
    int index = find(barcode);
    if (index < 0) return "Unknown barcode. Add this product to Cart.h and reflash.";
    if (remove) {
      if (!quantities[index]) return "This product is not in the cart.";
      --quantities[index];
    } else {
      if (quantities[index] >= 999) return "Quantity limit is 999 per product.";
      if (uint64_t(total()) + PRODUCTS[index].pricePaise > UINT32_MAX) return "Bill limit reached.";
      ++quantities[index];
    }
    return nullptr;
  }

  void clear() { memset(quantities, 0, sizeof(quantities)); }
};

// Runs on every device boot, before accepting a real cart request.
inline bool cartSelfTest() {
  Cart test;
  if (test.total() != 0 || test.change("99999999", false) == nullptr) return false;
  if (test.change(PRODUCTS[0].barcode, true) == nullptr) return false;
  if (test.change(PRODUCTS[0].barcode, false) || test.change(PRODUCTS[0].barcode, false)) return false;
  if (test.total() != PRODUCTS[0].pricePaise * 2) return false;
  if (test.change(PRODUCTS[0].barcode, true) || test.total() != PRODUCTS[0].pricePaise) return false;
  test.clear();
  for (unsigned i = 0; i < 999; ++i) {
    if (test.change(PRODUCTS[0].barcode, false)) return false;
  }
  if (test.change(PRODUCTS[0].barcode, false) == nullptr || test.quantities[0] != 999) return false;
  test.clear();
  return test.total() == 0;
}
