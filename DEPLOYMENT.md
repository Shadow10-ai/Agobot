# AgoBot — Render Deployment Guide

## Current Status
- **Frontend**: Live at https://agobot-frontend.onrender.com ✅
- **Backend**: Needs to be created on Render dashboard ← do this now

---

## Step 1: Push Code to GitHub
In the Emergent chat, click **"Save to Github"** to push all recent changes (Kraken migration).

---

## Step 2: Create the Backend Service on Render

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your **GitHub repository** (the AgoBot repo)
4. Configure:
   - **Name**: `agobot-backend`
   - **Region**: `Frankfurt (EU Central)` ← important, avoids US geo-blocks
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.prod.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Plan**: Free

---

## Step 3: Set Backend Environment Variables

In the Render dashboard for `agobot-backend`, go to **Environment** tab and add:

| Variable | Value |
|---|---|
| `MONGO_URL` | Your MongoDB Atlas connection string |
| `DB_NAME` | `agobot_prod` |
| `JWT_SECRET` | Any long random string (e.g. `agobot-super-secret-2026`) |
| `KRAKEN_API_KEY` | Your Kraken API key (from Kraken API Management) |
| `KRAKEN_API_SECRET` | Your Kraken API secret |

> ⚠️ Mark `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`, and `MONGO_URL` as **Secret** in Render.
> ⚠️ Never commit API keys to this file. Use Render's Environment tab only.

Click **"Create Web Service"** — Render will build and deploy automatically.

---

## Step 4: Get the Backend URL

Once the backend is running, Render assigns it a URL:
- Default: `https://agobot-backend.onrender.com`
- Or check the service page for the exact URL

---

## Step 5: Verify Deployment

```bash
curl https://agobot-backend.onrender.com/api/health
# Expected: {"status": "healthy", "database": "connected"}
```

---

## Step 6: Link Frontend to Backend (if needed)

If the frontend isn't showing data:
1. Go to `agobot-frontend` service on Render → **Environment**
2. Confirm `REACT_APP_BACKEND_URL` = `https://agobot-backend.onrender.com`
3. Trigger a **Manual Deploy** on the frontend

---

## Step 7: Switch to LIVE Mode

1. Open https://agobot-frontend.onrender.com
2. Log in → go to **Configuration**
3. Your Kraken keys are already saved in the database
4. Click the **LIVE** toggle — the bot will start real trading on Kraken

---

## Important Notes

- **Single worker**: `--workers 1` is intentional — the bot holds in-memory state
- **DRY mode first**: Run in DRY mode for a few hours to confirm the bot is trading correctly before switching LIVE
- **Frankfurt region**: Kraken is accessible from Render Frankfurt. No geo-blocking.
- **ML retraining**: The LightGBM model retrains automatically from MongoDB data on startup after 30+ labeled trades

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Frontend shows blank / no data | Check `REACT_APP_BACKEND_URL` is set correctly on the frontend service |
| `Cannot connect to MongoDB` | Check `MONGO_URL` — must start with `mongodb+srv://` for Atlas |
| Kraken connection fails | Check `KRAKEN_API_KEY` and `KRAKEN_API_SECRET` are set correctly |
| Bot not scanning | Check backend logs in Render dashboard for startup errors |
| Health check failing | Ensure start command includes `--host 0.0.0.0` |
