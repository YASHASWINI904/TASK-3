import os
import tempfile
import unittest
from unittest.mock import patch

import app as api

class FakeModel:
    pipeline = True
    metrics = {"accuracy": 0.75, "dataset_samples": 30, "training_samples": 22, "test_samples": 8, "labels": ["negative", "neutral", "positive"]}
    def load(self): return True
    def train(self): return self.metrics
    def predict(self, text):
        label = "negative" if any(x in text.lower() for x in ("bad", "terrible", "broken")) else "positive"
        return {"sentiment": label, "confidence": 0.8, "scores": {label: 0.8}}

class SentinelApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(api, "DB_PATH", os.path.join(self.tmp.name, "test.db"))
        self.db_patch.start()
        api.model = FakeModel()
        api.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        api.init_db()
        self.client = api.app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def register(self, email):
        return self.client.post("/api/auth/register", json={"name":"Test User","email":email,"password":"password123"})

    def test_registration_hashes_password_and_login(self):
        r=self.register("a@example.com")
        self.assertEqual(r.status_code,201)
        with api.db() as conn:
            row=conn.execute("SELECT password_hash FROM users WHERE email=?",
                             ("a@example.com",)).fetchone()
        self.assertNotEqual(row["password_hash"],"password123")
        self.client.post("/api/auth/logout")
        bad=self.client.post("/api/auth/login",json={"email":"a@example.com","password":"wrongpass"})
        self.assertEqual(bad.status_code,401)
        good=self.client.post("/api/auth/login",json={"email":"a@example.com","password":"password123"})
        self.assertEqual(good.status_code,200)

    def test_prediction_requires_login_and_is_saved(self):
        r=self.client.post("/api/predict",json={"text":"This is great"})
        self.assertEqual(r.status_code,401)
        self.register("a@example.com")
        r=self.client.post("/api/predict",json={"text":"This is great"})
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(self.client.get("/api/history").json),1)

    def test_users_cannot_read_each_others_history(self):
        self.register("a@example.com")
        self.client.post("/api/predict",json={"text":"great product"})
        self.client.post("/api/auth/logout")
        self.register("b@example.com")
        self.assertEqual(self.client.get("/api/history").json,[])

    def test_validation_and_insights(self):
        self.register("a@example.com")
        self.assertEqual(self.client.post("/api/predict",json={"text":" "}).status_code,400)
        self.client.post("/api/predict",json={"text":"terrible product"})
        self.assertEqual(self.client.get("/api/insights").status_code,200)
        self.assertEqual(self.client.get("/api/export.csv").status_code,200)

    def test_alerts_are_persisted_and_user_scoped(self):
        self.register("a@example.com")
        for _ in range(3):
            self.client.post("/api/predict", json={"text":"bad delivery delay"})
        insights = self.client.get("/api/insights").json
        self.assertTrue(any(a["topic"] == "Delivery" for a in insights["alerts"]))
        alert = next(a for a in insights["alerts"] if a["topic"] == "Delivery")
        updated = self.client.patch(f"/api/alerts/{alert['id']}", json={"status":"acknowledged"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["alert"]["status"], "acknowledged")
        self.client.post("/api/auth/logout")
        self.register("b@example.com")
        self.assertEqual(self.client.patch(f"/api/alerts/{alert['id']}", json={"status":"resolved"}).status_code, 404)

    def test_alert_status_validation(self):
        self.register("a@example.com")
        response = self.client.patch("/api/alerts/1", json={"status":"anything"})
        self.assertEqual(response.status_code, 400)

    def test_account_settings_persist_and_validate_preferences(self):
        self.register("a@example.com")
        defaults = self.client.get("/api/settings")
        self.assertEqual(defaults.status_code, 200)
        self.assertEqual(defaults.json["default_page"], "Overview")
        self.assertEqual(defaults.json["refresh_interval"], "10")

        updated = self.client.put("/api/settings", json={
            "notifications": False,
            "theme": "light",
            "default_page": "Risk Radar",
            "refresh_interval": "30",
        })
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["default_page"], "Risk Radar")
        self.assertEqual(updated.json["refresh_interval"], "30")
        self.assertEqual(self.client.get("/api/settings").json["theme"], "light")

        invalid_page = self.client.put("/api/settings", json={"default_page":"Unknown"})
        invalid_refresh = self.client.put("/api/settings", json={"refresh_interval":"5"})
        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(invalid_refresh.status_code, 400)

    def test_settings_schema_migrates_existing_accounts(self):
        self.register("a@example.com")
        with api.db() as conn:
            conn.execute("DROP TABLE user_settings")
            conn.execute("""CREATE TABLE user_settings (
                user_id INTEGER PRIMARY KEY, notifications INTEGER NOT NULL DEFAULT 1,
                theme TEXT NOT NULL DEFAULT 'dark', updated_at TEXT NOT NULL)""")
            conn.execute("INSERT INTO user_settings(user_id,updated_at) VALUES(1,'2026-01-01')")

        api.init_db()
        settings = self.client.get("/api/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json["default_page"], "Overview")
        self.assertEqual(settings.json["refresh_interval"], "10")

if __name__ == "__main__":
    unittest.main()
