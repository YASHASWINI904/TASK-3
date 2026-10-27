import json
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:5000/api"

class Client:
    def __init__(self):
        self.cookies = {}
    def request(self, path, payload=None, method=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
        if method: req.method = method
        if self.cookies:
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read().decode()
                self._cookies(response.headers)
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            self._cookies(exc.headers)
            body = exc.read().decode()
            return exc.code, json.loads(body) if body else {}
    def _cookies(self, headers):
        for item in headers.get_all("Set-Cookie", []) or []:
            pair = item.split(";", 1)[0]
            if "=" in pair:
                key, value = pair.split("=", 1); self.cookies[key] = value

client = Client()
status, health = client.request("/health")
assert status == 200 and health.get("status") == "ok", f"Health failed: {health}"
print("Health: OK")
status, model = client.request("/model")
assert status == 200, f"Model endpoint failed: {model}"
print("Model loaded:", model.get("loaded"))
email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
status, account = client.request("/auth/register", {"name":"Smoke Test", "email":email, "password":"TestPass123!"})
assert status == 201, f"Registration failed: {account}"
status, prediction = client.request("/predict", {"text":"The product is excellent and I love it"})
assert status == 200, f"Prediction failed: {prediction}"
print("Prediction:", prediction.get("sentiment"), "confidence:", prediction.get("confidence"))
status, history = client.request("/history")
assert status == 200 and len(history) >= 1, f"History failed: {history}"
print("History records:", len(history))
print("All smoke tests passed.")
