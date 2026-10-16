#include <WiFi.h>
#include <WebServer.h>
#include <esp_system.h>
#include "Cart.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

WebServer server(80);
Cart cart;
String bootSession;

struct Receipt { String id; String command; };
// shortcut: retain 32 request IDs in RAM; use durable receipts for multiple production clients.
Receipt receipts[32];
unsigned nextReceipt = 0;

String jsonString(const String& value) {
  String result = "\"";
  for (unsigned i = 0; i < value.length(); ++i) {
    char ch = value[i];
    if (ch == '"' || ch == '\\') result += '\\';
    if (uint8_t(ch) < 32) { result += ' '; continue; }
    result += ch;
  }
  return result + '"';
}

void errorResponse(int status, const String& message) {
  server.send(status, "application/json", "{\"error\":" + jsonString(message) + "}");
}

bool authorized() {
  if (server.header("X-API-Key") == API_TOKEN) return true;
  errorResponse(401, "Invalid API token.");
  return false;
}

bool isDigits(const String& value) {
  if (value.length() < 1 || value.length() > 32) return false;
  for (unsigned i = 0; i < value.length(); ++i) {
    if (value[i] < '0' || value[i] > '9') return false;
  }
  return true;
}

void sendCart() {
  String json = "{\"session\":" + jsonString(bootSession) + ",\"items\":[";
  bool first = true;
  for (unsigned i = 0; i < PRODUCT_COUNT; ++i) {
    if (!cart.quantities[i]) continue;
    if (!first) json += ',';
    first = false;
    json += "{\"barcode\":" + jsonString(PRODUCTS[i].barcode);
    json += ",\"name\":" + jsonString(PRODUCTS[i].name);
    json += ",\"price_paise\":" + String(PRODUCTS[i].pricePaise);
    json += ",\"quantity\":" + String(cart.quantities[i]) + '}';
  }
  json += "],\"total_paise\":" + String(cart.total()) + '}';
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

void mutate(bool clearCart) {
  if (!authorized()) return;
  if (server.arg("session") != bootSession) {
    errorResponse(409, "ESP32 restarted. Refresh the bill before scanning again.");
    return;
  }
  String id = server.arg("request_id");
  if (id.length() != 32) { errorResponse(400, "request_id must be 32 hexadecimal characters."); return; }
  for (unsigned i = 0; i < id.length(); ++i) {
    char ch = id[i];
    if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f') || (ch >= 'A' && ch <= 'F'))) {
      errorResponse(400, "Invalid request_id."); return;
    }
  }
  String barcode = server.arg("barcode");
  String action = server.arg("action");
  if (!clearCart && (!isDigits(barcode) || (action != "add" && action != "remove"))) {
    errorResponse(400, "Use a numeric barcode and action add or remove.");
    return;
  }
  String command = clearCart ? "clear" : action + ':' + barcode;
  for (const auto& receipt : receipts) {
    if (receipt.id == id) {
      if (receipt.command != command) errorResponse(409, "request_id reused for a different operation.");
      else sendCart();
      return;
    }
  }
  if (clearCart) cart.clear();
  else {
    const char* error = cart.change(barcode.c_str(), action == "remove");
    if (error) { errorResponse(422, error); return; }
  }
  receipts[nextReceipt] = {id, command};
  nextReceipt = (nextReceipt + 1) % 32;
  sendCart();
  Serial.printf("Cart total: INR %lu.%02lu\n", (unsigned long)(cart.total() / 100), (unsigned long)(cart.total() % 100));
}

void halt(const char* message) {
  Serial.println(message);
  while (true) delay(1000);
}

void setup() {
  Serial.begin(115200);
  if (!cartSelfTest()) halt("Cart self-test FAILED. Server disabled.");
  Serial.println("Cart self-test passed.");
  if (strcmp(WIFI_SSID, "YOUR_WIFI_SSID") == 0 || strcmp(API_TOKEN, "REPLACE_WITH_RANDOM_ALPHANUMERIC_TOKEN") == 0) {
    halt("Set WIFI_SSID, WIFI_PASSWORD and API_TOKEN in secrets.h, then upload again.");
  }
  String token = API_TOKEN;
  if (token.length() < 16 || token.length() > 128) halt("API_TOKEN must contain 16-128 alphanumeric characters.");
  for (unsigned i = 0; i < token.length(); ++i) {
    char ch = token[i];
    if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z'))) halt("API_TOKEN must be alphanumeric.");
  }
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  // shortcut: Wi-Fi retries indefinitely; add provisioning if credentials must change without reflashing.
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print('.'); }
  char session[17];
  snprintf(session, sizeof(session), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  bootSession = session;
  Serial.print("\nESP32 address: http://");
  Serial.println(WiFi.localIP());
  const char* headers[] = {"X-API-Key"};
  server.collectHeaders(headers, 1);
  server.on("/api/cart", HTTP_GET, [] { if (authorized()) sendCart(); });
  server.on("/api/scan", HTTP_POST, [] { mutate(false); });
  server.on("/api/clear", HTTP_POST, [] { mutate(true); });
  server.onNotFound([] { errorResponse(404, "Unknown endpoint."); });
  server.begin();
}

void loop() {
  server.handleClient();
  delay(2);
}
