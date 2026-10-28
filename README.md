# Sentinel AI — Content Intelligence & Early-Warning Radar

## Quick Start (Windows — recommended for evaluators)

### Requirements
- Windows 10/11
- Python 3.10 or newer
- Node.js 18 or newer (npm is included with Node.js)
- Internet connection on first launch so dependencies can be installed

### Run the application
1. Extract the complete ZIP file.
2. Open the extracted `Sentinel_AI` folder.
3. Double-click `START_SENTINEL_AI.bat`.
   - Alternatively, open Command Prompt in this folder and run: `START_SENTINEL_AI.bat`
4. Wait while the script prepares dependencies and starts the backend and frontend in separate terminal windows.
5. When the frontend is ready, open `http://127.0.0.1:5173` in your browser.
6. Register an account and try the available features.

Keep both service terminal windows open while using the application. The first launch can take several minutes. If an error occurs, keep the terminal windows open and read the error message. Confirm Python and Node.js are installed by running `py --version` and `node --version` in Command Prompt.

## Run from the VS Code integrated terminal
1. In VS Code, choose **File → Open Folder** and select the extracted `Sentinel_AI` folder.
2. Choose **Terminal → New Terminal**.
3. Run ` .\START_SENTINEL_AI.bat ` (without the surrounding spaces) in the terminal. If using PowerShell and that form is rejected, run `cmd /c START_SENTINEL_AI.bat`.
4. Open `http://127.0.0.1:5173` after the frontend reports that it is ready.

## Project overview
Sentinel AI is a full-stack educational NLP application using React + Vite, Flask, scikit-learn TF-IDF + Logistic Regression, and SQLite. The training dataset is read with Python's built-in CSV module, so pandas is not required.

Implemented features include:
- Account registration and login with server-side password hashing and HTTP-only session cookies.
- Private per-account analysis history and profile/account settings.
- Single-text and batch sentiment analysis.
- Model status and held-out evaluation metrics.
- Early-warning topic overview and alert records for human review.
- Search and sentiment filtering in history, export, and deletion actions.
- Responsive dashboard with dark/light themes, analysis workspace, batch analysis, history, profile, account settings, radar, and model/API pages.

## Important limitations
This is a demo/internship baseline, not a production security or moderation system. The included dataset is small and synthetic/educational; metrics may overestimate real-world performance. Sentiment predictions are not safety-category classification. The radar analyzes only records submitted to this app; it does not monitor social media. Alerts are signals for human review, not validated forecasts. Production deployment requires additional security hardening and HTTPS.

## Backend tests
From the `backend` folder, run:

```powershell
python -m unittest discover -s tests -v
```

## API endpoints
- `GET /api/health`, `GET /api/model`
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `PATCH /api/profile`
- `GET /api/settings`, `PUT /api/settings`
- `POST /api/predict`, `POST /api/predict/batch`, `POST /api/train`
- `GET /api/history?q=&sentiment=&limit=`, `DELETE /api/history`, `DELETE /api/history/<id>`
- `GET /api/insights`, `GET /api/alerts`, `PATCH /api/alerts/<id>`
- `GET /api/export.csv`

The application runs locally on the computer where it is started. The local URL is not publicly accessible from other computers unless the application is deployed or network access is configured separately.

## Cloud Deployment Guide

This project is pre-configured for seamless cloud deployment:

### 1. Deploying Frontend to Vercel
1. Import your GitHub repository (`TASK-3`) into **Vercel**.
2. Vercel will automatically use the included `vercel.json` and build the frontend.
3. In **Environment Variables**, set:
   - `VITE_API_BASE_URL`: URL of your deployed backend (e.g. `https://your-backend.onrender.com/api`).
4. Click **Deploy**.

### 2. Deploying Frontend to Netlify
1. Connect the repository to **Netlify**.
2. Netlify will auto-detect the root `netlify.toml` (Base directory: `frontend`, Build command: `npm run build`, Publish directory: `frontend/dist`).
3. Set `VITE_API_BASE_URL` in **Site settings → Environment variables**.
4. Click **Deploy site**.

### 3. Deploying Backend (e.g., Render or Railway)
- **Render**: Connect repository and select Blueprint deployment using the included `render.yaml`, or create a Python Web Service:
  - Root directory: `backend`
  - Build command: `pip install -r requirements.txt`
  - Start command: `gunicorn app:app -b 0.0.0.0:$PORT`
  - Environment variables:
    - `SECRET_KEY`: `<random string>`
    - `COOKIE_SECURE`: `true`
    - `CORS_ORIGINS`: `https://your-frontend.vercel.app` (your frontend domain)
