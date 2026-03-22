# AgoBot — Railway Deployment Guide

## Overview
AgoBot deploys as **3 services** on Railway:
1. **Backend** — FastAPI + ML (Python)
2. **Frontend** — React (served via nginx)
3. **MongoDB** — Railway managed database plugin

---

## Step 1: Push Code to GitHub

In the Emergent chat, click **"Save to Github"** to push your code to a GitHub repo (if not already done).

---

## Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Choose **Deploy from GitHub repo** → select your AgoBot repository

---

## Step 3: Add MongoDB Database

1. In your Railway project canvas, click **"+ New"**
2. Select **Database → Add MongoDB**
3. Railway auto-creates a MongoDB instance and exposes `MONGO_URL` and `MONGOHOST` etc.
4. Click the MongoDB service → **Variables** tab → copy the `MONGO_URL` value (you'll need it for backend)

> **Alternative**: Use MongoDB Atlas (free tier) at [cloud.mongodb.com](https://cloud.mongodb.com). Create a cluster, get the connection string, and use that as `MONGO_URL`.

---

## Step 4: Configure the Backend Service

Railway will auto-detect the root `/` of your repo. You need to point it to `/backend`:

1. Click your main service → **Settings** → **Source** → set **Root Directory** to `backend`
2. Railway will now use `backend/Dockerfile` automatically

### Set Backend Environment Variables

Go to your backend service → **Variables** tab → add:

| Variable | Value | Notes |
|---|---|---|
| `MONGO_URL` | `mongodb://...` | From Railway MongoDB plugin or Atlas |
| `DB_NAME` | `agobot_prod` | Your database name |
| `JWT_SECRET` | *(generate below)* | Must be strong random string |
| `BINANCE_API_KEY` | *(your Binance key)* | From Binance API Management |
| `BINANCE_API_SECRET` | *(your Binance secret)* | Mark as **Secret** in Railway |
| `PORT` | `8001` | Railway may override this automatically |

**Generate a strong JWT_SECRET:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Step 5: Deploy the Frontend Service

1. In Railway canvas, click **"+ New"** → **GitHub Repo** → same repo → click **Add Service**
2. Set **Root Directory** to `frontend`
3. Railway will use `frontend/Dockerfile`

### Set Frontend Environment Variables

Go to the frontend service → **Variables** tab → add:

| Variable | Value | Notes |
|---|---|---|
| `REACT_APP_BACKEND_URL` | *(set after backend is live)* | The backend's public Railway URL |

---

## Step 6: Get Backend Public URL & Link Frontend

1. Deploy the backend first (click **Deploy** on the backend service)
2. Once running, go to backend service → **Settings** → **Networking** → **Generate Domain**
3. Copy the domain (e.g. `https://agobot-backend.up.railway.app`)
4. Go to the **frontend service** → Variables → set:
   ```
   REACT_APP_BACKEND_URL=https://agobot-backend.up.railway.app
   ```
5. Redeploy the frontend (variables are baked into the React build)

---

## Step 7: Generate Frontend Domain

1. Go to frontend service → **Settings** → **Networking** → **Generate Domain**
2. Your app will be live at e.g. `https://agobot-frontend.up.railway.app`

---

## Step 8: Verify Deployment

1. Open the frontend URL in your browser
2. Register/login
3. Dashboard should show bot scanning
4. Go to Config → toggle to **LIVE mode** — Binance should now connect (no geo-restriction on Railway IPs)

### Quick API Health Check
```bash
curl https://agobot-backend.up.railway.app/api/health
# Expected: {"status": "healthy", "database": "connected"}
```

---

## Environment Variables Summary

### Backend (required)
```env
MONGO_URL=mongodb://...
DB_NAME=agobot_prod
JWT_SECRET=<strong-random-string>
BINANCE_API_KEY=<your-key>
BINANCE_API_SECRET=<your-secret>
```

### Frontend (required)
```env
REACT_APP_BACKEND_URL=https://<your-backend>.up.railway.app
```

---

## Important Notes

- **Single worker**: The backend uses `--workers 1` — this is intentional. The bot loop holds in-memory state (`bot_state`, `ml_model_state`, `_circuit_breaker`) that must not be split across multiple worker processes.
- **ML training**: LightGBM model trains automatically after 5 labeled trades. Railway's servers have no geo-restrictions, so full Binance live data and ML functionality will work.
- **LIVE mode**: Will work on Railway because IP is not geo-restricted by Binance.
- **Persistent storage**: ML model (`ml_model.joblib`) is saved to disk. On Railway, this resets on redeployment. The model retrains automatically from MongoDB data on startup, so this is not a problem.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Frontend shows blank page | Ensure `REACT_APP_BACKEND_URL` is set and doesn't have a trailing slash |
| `Cannot connect to MongoDB` | Check `MONGO_URL` format — must use `mongodb+srv://` for Atlas or plain `mongodb://` for Railway plugin |
| Binance connection fails | Check `BINANCE_API_KEY` / `BINANCE_API_SECRET` are set and not restricted to specific IPs in Binance settings |
| Bot not scanning | Check backend logs in Railway dashboard for errors |
| ML model not training | Need at least 30 labeled trades — run in DRY mode for a few hours first |
