from flask import Flask, request, jsonify, session
from flask_cors import CORS
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, os
from contextlib import contextmanager
from dotenv import load_dotenv
from datetime import datetime, timezone
from model_service import SentimentModel

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / '.env')
DB_PATH = BASE_DIR / "sentiment_history.db"
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-change-this-secret"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
)

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/api/*": {
            "origins": [
                "https://task-3-sentinel-aif.onrender.com",
                "http://localhost:5173",
                "http://127.0.0.1:5173"
            ]
        }
    }
)

model = SentimentModel()

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def now():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_settings (
          user_id INTEGER PRIMARY KEY, notifications INTEGER NOT NULL DEFAULT 1,
          theme TEXT NOT NULL DEFAULT 'dark', default_page TEXT NOT NULL DEFAULT 'Overview',
          refresh_interval TEXT NOT NULL DEFAULT '10', updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id))""")
        settings_columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_settings)")}
        if "default_page" not in settings_columns:
            conn.execute("ALTER TABLE user_settings ADD COLUMN default_page TEXT NOT NULL DEFAULT 'Overview'")
        if "refresh_interval" not in settings_columns:
            conn.execute("ALTER TABLE user_settings ADD COLUMN refresh_interval TEXT NOT NULL DEFAULT '10'")
        conn.execute("""CREATE TABLE IF NOT EXISTS predictions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT NOT NULL,
          sentiment TEXT NOT NULL, confidence REAL NOT NULL, scores_json TEXT NOT NULL,
          created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_user_created ON predictions(user_id, created_at)")
        # Existing history is retained as demo data, but not exposed to new user accounts.
        conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, topic TEXT NOT NULL,
          severity TEXT NOT NULL, current_rate REAL NOT NULL, baseline_rate REAL NOT NULL,
          explanation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id))""")

def require_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with db() as conn:
        return conn.execute("SELECT id,name,email,created_at FROM users WHERE id=?", (uid,)).fetchone()

def user_json(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}

def validate_text(value):
    if not isinstance(value, str) or not value.strip(): return None, "Please provide non-empty text."
    value = value.strip()
    if len(value) > 5000: return None, "Text must be 5,000 characters or fewer."
    return value, None

def save_prediction(text, result, uid):
    with db() as conn:
        cur = conn.execute("INSERT INTO predictions (user_id,text,sentiment,confidence,scores_json,created_at) VALUES (?,?,?,?,?,?)",
            (uid,text,result["sentiment"],result["confidence"],json.dumps(result["scores"]),now()))
        return {"id":cur.lastrowid,"text":text,**result,"created_at":now()}

@app.get("/api/health")
def health():
    return jsonify({"status":"ok","service":"Sentinel AI NLP REST API","timestamp":now()})

@app.post("/api/auth/register")
def register():
    p=request.get_json(silent=True) or {}
    name=str(p.get("name","")).strip(); email=str(p.get("email","")).strip().lower()
    password=p.get("password","")
    if len(name)<2: return jsonify(error="Please enter your full name."),400
    if "@" not in email or "." not in email.split("@")[-1]: return jsonify(error="Enter a valid email address."),400
    if not isinstance(password,str) or len(password)<8: return jsonify(error="Password must be at least 8 characters."),400
    try:
        with db() as conn:
            cur=conn.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                (name,email,generate_password_hash(password),now()))
            uid=cur.lastrowid
            conn.execute("INSERT INTO user_settings(user_id,updated_at) VALUES(?,?)",(uid,now()))
        session.clear(); session["user_id"]=uid
        return jsonify(user={"id":uid,"name":name,"email":email},message="Account created."),201
    except sqlite3.IntegrityError:
        return jsonify(error="An account with this email already exists."),409

@app.post("/api/auth/login")
def login():
    p=request.get_json(silent=True) or {}; email=str(p.get("email","")).strip().lower(); password=p.get("password","")
    with db() as conn: row=conn.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"],password if isinstance(password,str) else ""):
        return jsonify(error="Invalid email or password."),401
    session.clear(); session["user_id"]=row["id"]
    return jsonify(user=user_json(row),message="Signed in.")

@app.post("/api/auth/logout")
def logout():
    session.clear(); return jsonify(message="Signed out.")

@app.get("/api/auth/me")
def me():
    row=require_user()
    return (jsonify(user=user_json(row)),200) if row else (jsonify(error="Authentication required."),401)

@app.patch("/api/profile")
def profile():
    row=require_user()
    if not row:return jsonify(error="Authentication required."),401
    p=request.get_json(silent=True) or {}; name=str(p.get("name","")).strip(); email=str(p.get("email","")).strip().lower()
    if len(name)<2 or "@" not in email:return jsonify(error="Enter a valid name and email."),400
    try:
        with db() as conn: conn.execute("UPDATE users SET name=?,email=? WHERE id=?",(name,email,row["id"]))
        with db() as conn: updated=conn.execute("SELECT id,name,email,created_at FROM users WHERE id=?",(row["id"],)).fetchone()
        return jsonify(user=user_json(updated))
    except sqlite3.IntegrityError:return jsonify(error="That email is already in use."),409

@app.get("/api/settings")
def get_settings():
    row=require_user()
    if not row:return jsonify(error="Authentication required."),401
    with db() as conn: s=conn.execute("SELECT notifications,theme,default_page,refresh_interval FROM user_settings WHERE user_id=?",(row["id"],)).fetchone()
    return jsonify(notifications=bool(s["notifications"]),theme=s["theme"],default_page=s["default_page"],refresh_interval=s["refresh_interval"])

@app.put("/api/settings")
def put_settings():
    row=require_user()
    if not row:return jsonify(error="Authentication required."),401
    p=request.get_json(silent=True) or {}; theme=p.get("theme","dark")
    if theme not in ("dark","light"):return jsonify(error="Theme must be dark or light."),400
    notifications=p.get("notifications",True)
    if not isinstance(notifications,bool):return jsonify(error="Notifications must be enabled or disabled."),400
    default_page=p.get("default_page","Overview")
    if default_page not in ("Overview","Sentiment Analyzer","Prediction History","Risk Radar"):
        return jsonify(error="Choose a valid default page."),400
    refresh_interval=p.get("refresh_interval","10")
    if refresh_interval not in ("off","10","30","60"):
        return jsonify(error="Choose a valid dashboard refresh interval."),400
    with db() as conn:
        conn.execute("UPDATE user_settings SET notifications=?,theme=?,default_page=?,refresh_interval=?,updated_at=? WHERE user_id=?",
            (int(notifications),theme,default_page,refresh_interval,now(),row["id"]))
    return jsonify(message="Settings saved.",notifications=notifications,theme=theme,default_page=default_page,refresh_interval=refresh_interval)

@app.get("/api/model")
def model_status():
    return jsonify({"loaded":model.pipeline is not None,"algorithm":"TF-IDF + Logistic Regression","metrics":model.metrics,
      "model_file_exists":(BASE_DIR/"model"/"sentiment_pipeline.joblib").exists(),
      "limitations":"Educational sentiment classifier trained on a small sample dataset. It does not classify safety categories or reliably detect sarcasm."})

@app.post("/api/train")
def train():
    if not require_user():return jsonify(error="Authentication required."),401
    try:return jsonify(message="Model trained and saved successfully.",metrics=model.train())
    except Exception as exc:app.logger.exception("Training failed");return jsonify(error="Training failed",details=str(exc)),500

@app.post("/api/predict")
def predict():
    user=require_user()
    if not user:return jsonify(error="Authentication required."),401
    p=request.get_json(silent=True) or {}; text,error=validate_text(p.get("text"))
    if error:return jsonify(error=error),400
    try:return jsonify(save_prediction(text,model.predict(text),user["id"]))
    except RuntimeError as exc:return jsonify(error=str(exc)),503
    except Exception:app.logger.exception("Prediction failed");return jsonify(error="Prediction failed"),500

@app.post("/api/predict/batch")
def predict_batch():
    user=require_user()
    if not user:return jsonify(error="Authentication required."),401
    p=request.get_json(silent=True) or {}; texts=p.get("texts")
    if not isinstance(texts,list) or not texts:return jsonify(error="Provide a non-empty 'texts' array."),400
    if len(texts)>100:return jsonify(error="Batch limit is 100 texts."),400
    results=[]; errors=[]
    for i,item in enumerate(texts):
        text,error=validate_text(item)
        if error:errors.append({"index":i,"error":error});continue
        results.append(save_prediction(text,model.predict(text),user["id"]))
    return jsonify(results=results,errors=errors,processed=len(results))

@app.get("/api/history")
def history():
    user=require_user()
    if not user:return jsonify(error="Authentication required."),401
    try:limit=min(max(int(request.args.get("limit",100)),1),500)
    except ValueError:limit=100
    q=str(request.args.get("q","")).strip(); sentiment=str(request.args.get("sentiment","")).lower()
    sql="SELECT * FROM predictions WHERE user_id=?"; args=[user["id"]]
    if q:sql+=" AND text LIKE ?";args.append("%"+q+"%")
    if sentiment in ("positive","negative","neutral"):sql+=" AND sentiment=?";args.append(sentiment)
    sql+=" ORDER BY id DESC LIMIT ?";args.append(limit)
    with db() as conn:rows=conn.execute(sql,args).fetchall()
    return jsonify([{"id":r["id"],"text":r["text"],"sentiment":r["sentiment"],"confidence":r["confidence"],"scores":json.loads(r["scores_json"]),"created_at":r["created_at"]} for r in rows])

@app.delete("/api/history")
def clear_history():
    user=require_user()
    if not user:return jsonify(error="Authentication required."),401
    with db() as conn:conn.execute("DELETE FROM predictions WHERE user_id=?",(user["id"],))
    return jsonify(message="Your prediction history was cleared.")

@app.delete("/api/history/<int:record_id>")
def delete_record(record_id):
    user=require_user()
    if not user:return jsonify(error="Authentication required."),401
    with db() as conn:cur=conn.execute("DELETE FROM predictions WHERE id=? AND user_id=?",(record_id,user["id"]))
    if not cur.rowcount:return jsonify(error="Record not found."),404
    return jsonify(message="Record deleted.")

@app.get("/api/insights")
def insights():
    user = require_user()
    if not user:
        return jsonify(error="Authentication required."), 401

    # Compare the most recent 7 days with the preceding 7 days. This uses
    # submitted records only; it is not live monitoring or a statistical forecast.
    from datetime import timedelta
    current_time = datetime.now(timezone.utc)
    recent_start = current_time - timedelta(days=7)
    baseline_start = current_time - timedelta(days=14)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, sentiment, created_at, text FROM predictions WHERE user_id=? ORDER BY created_at DESC",
            (user["id"],)
        ).fetchall()

    def in_window(row, start, end):
        try:
            stamp = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return start <= stamp < end
        except (ValueError, TypeError):
            return False

    recent = [r for r in rows if in_window(r, recent_start, current_time)]
    baseline = [r for r in rows if in_window(r, baseline_start, recent_start)]
    buckets = {
        "Product quality": ["quality", "broken", "broke", "defect", "durable", "damaged"],
        "Delivery": ["delivery", "arrived", "shipping", "late", "delay", "package"],
        "Customer service": ["support", "service", "help", "staff", "rude", "response"],
        "Price": ["price", "cost", "expensive", "cheap", "value", "refund"],
        "Reliability": ["reliable", "works", "work", "failure", "crash", "battery", "stopped"]
    }
    topics = []
    alert_candidates = []
    all_text_rows = list(rows)
    for topic, words in buckets.items():
        def matches(records):
            return [r for r in records if any(w in r["text"].lower() for w in words)]
        topic_rows = matches(all_text_rows)
        recent_rows = matches(recent)
        baseline_rows = matches(baseline)
        if not topic_rows:
            continue
        negative = sum(r["sentiment"] == "negative" for r in topic_rows)
        recent_negative = sum(r["sentiment"] == "negative" for r in recent_rows)
        baseline_negative = sum(r["sentiment"] == "negative" for r in baseline_rows)
        overall_rate = negative / len(topic_rows)
        recent_rate = recent_negative / len(recent_rows) if recent_rows else 0.0
        baseline_rate = baseline_negative / len(baseline_rows) if baseline_rows else 0.0
        item = {
            "topic": topic, "mentions": len(topic_rows), "negative": negative,
            "negative_rate": round(overall_rate, 3), "sample_size": len(topic_rows),
            "recent_mentions": len(recent_rows), "recent_negative": recent_negative,
            "recent_negative_rate": round(recent_rate, 3),
            "baseline_mentions": len(baseline_rows),
            "baseline_negative_rate": round(baseline_rate, 3),
            "change_percentage_points": round((recent_rate - baseline_rate) * 100, 1),
            "supporting_record_ids": [r["id"] for r in recent_rows[:10]]
        }
        topics.append(item)
        # Require a minimum sample. With no baseline, only show a watch signal
        # when enough recent records exist; never invent a percentage increase.
        qualifies = len(recent_rows) >= 3 and recent_rate >= 0.6
        if qualifies:
            severity = "high" if recent_rate >= 0.8 and len(recent_rows) >= 5 else "medium"
            baseline_label = f"{baseline_negative}/{len(baseline_rows)} negative" if baseline_rows else "no prior-window baseline"
            explanation = (
                f"{recent_negative} of {len(recent_rows)} matching records from the last 7 days "
                f"were classified negative; previous 7-day baseline: {baseline_label}. "
                "Keyword-based signal; inspect records before acting."
            )
            alert_candidates.append({
                "topic": topic, "severity": severity, "current_rate": round(recent_rate, 3),
                "baseline_rate": round(baseline_rate, 3), "mentions": len(recent_rows),
                "explanation": explanation, "supporting_record_ids": item["supporting_record_ids"]
            })

    # Persist one open/acknowledged alert per user+topic+current 7-day window.
    with db() as conn:
        for candidate in alert_candidates:
            existing = conn.execute(
                "SELECT id FROM alerts WHERE user_id=? AND topic=? AND created_at>=?",
                (user["id"], candidate["topic"], recent_start.isoformat())
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE alerts SET severity=?,current_rate=?,baseline_rate=?,explanation=? WHERE id=? AND user_id=?",
                    (candidate["severity"], candidate["current_rate"], candidate["baseline_rate"],
                     candidate["explanation"], existing["id"], user["id"])
                )
            else:
                conn.execute(
                    "INSERT INTO alerts(user_id,topic,severity,current_rate,baseline_rate,explanation,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user["id"], candidate["topic"], candidate["severity"], candidate["current_rate"],
                     candidate["baseline_rate"], candidate["explanation"], "open", now())
                )

    topics.sort(key=lambda x: (x["recent_negative_rate"], x["recent_mentions"], x["negative_rate"]), reverse=True)
    total = len(rows)
    negative_total = sum(r["sentiment"] == "negative" for r in rows)
    with db() as conn:
        saved_alerts = conn.execute(
            "SELECT id,topic,severity,current_rate,baseline_rate,explanation,status,created_at FROM alerts WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
            (user["id"],)
        ).fetchall()
    alerts = [{"id": a["id"], "topic": a["topic"], "severity": a["severity"],
               "current_rate": a["current_rate"], "baseline_rate": a["baseline_rate"],
               "explanation": a["explanation"], "status": a["status"], "created_at": a["created_at"]}
              for a in saved_alerts]
    return jsonify(
        total=total, negative_rate=round(negative_total / total, 3) if total else 0,
        topics=topics, alerts=alerts,
        windows={"recent_days": 7, "baseline_days": 7, "recent_start": recent_start.isoformat(),
                 "baseline_start": baseline_start.isoformat(), "generated_at": now()},
        note="Topics are keyword-based and use your submitted records only. Alerts require at least three matching records in the recent 7-day window; small samples can be misleading. No live monitoring is performed."
    )

@app.get("/api/alerts")
def get_alerts():
    user = require_user()
    if not user:
        return jsonify(error="Authentication required."), 401
    with db() as conn:
        rows = conn.execute(
            "SELECT id,topic,severity,current_rate,baseline_rate,explanation,status,created_at FROM alerts WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
            (user["id"],)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.patch("/api/alerts/<int:alert_id>")
def update_alert(alert_id):
    user = require_user()
    if not user:
        return jsonify(error="Authentication required."), 401
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in ("open", "acknowledged", "resolved"):
        return jsonify(error="Status must be open, acknowledged, or resolved."), 400
    with db() as conn:
        cur = conn.execute("UPDATE alerts SET status=? WHERE id=? AND user_id=?", (status, alert_id, user["id"]))
        row = conn.execute("SELECT id,topic,severity,current_rate,baseline_rate,explanation,status,created_at FROM alerts WHERE id=? AND user_id=?", (alert_id, user["id"])).fetchone()
    if not cur.rowcount:
        return jsonify(error="Alert not found."), 404
    return jsonify(alert=dict(row), message="Alert status updated.")

@app.get("/api/export.csv")
def export_csv():
    user=require_user()
    if not user:return jsonify(error="Authentication required."),401
    from flask import Response
    import csv,io
    with db() as conn:rows=conn.execute("SELECT id,text,sentiment,confidence,created_at FROM predictions WHERE user_id=? ORDER BY id DESC",(user["id"],)).fetchall()
    output=io.StringIO();writer=csv.writer(output);writer.writerow(["id","text","sentiment","confidence","created_at"])
    writer.writerows([tuple(r) for r in rows])
    return Response(output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=sentinel-analysis-history.csv"})

@app.errorhandler(404)
def not_found(_):return jsonify(error="Route not found."),404
@app.errorhandler(405)
def method_not_allowed(_):return jsonify(error="Method not allowed."),405

init_db()
try:
    if not model.load():model.train()
except Exception as exc: app.logger.exception("Model initialization failed")

if __name__=="__main__":
    print("Sentinel AI API: http://127.0.0.1:5000")
    app.run(host="127.0.0.1",port=5000,debug=os.environ.get("FLASK_DEBUG")=="1")
