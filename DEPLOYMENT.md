# 🚀 Multi-Cloud Deployment Guide

This repository supports deployment across multiple cloud platforms:
1. **AWS EC2 (Docker / Full Stack)**
2. **GitHub Pages (Frontend)** + **Cloud Backend**
3. **Firebase Hosting (Frontend)** + **Google Cloud Run (Backend)**
4. **Vercel (Frontend)** + **Cloud Backend**

---

## 1. 📦 AWS EC2 Deployment (Docker Compose)

### Prerequisites
- AWS EC2 Instance (Ubuntu 22.04 LTS recommended)
- Inbound Security Group rules for ports: `80` (HTTP), `443` (HTTPS), `8000` (FastAPI WS), `3000` (Frontend)

### Deployment Steps
```bash
# Clone or pull latest code
cd /home/ubuntu/Tamil-and-Sinhala-Converter
git pull origin main

# Build and launch containers
docker compose up -d --build
```

---

## 2. 🐙 GitHub Pages Deployment (Frontend)

Automated deployment via GitHub Actions (`.github/workflows/deploy-frontend.yml`).

### Setup
1. Go to **Settings** -> **Secrets and variables** -> **Actions**.
2. Add Secret `VITE_WS_URL`: `wss://your-backend-domain.com`.
3. Go to **Settings** -> **Pages** and set **Source** to `GitHub Actions`.
4. Push to `main` branch to trigger auto-deployment.

---

## 3. 🔥 Firebase Hosting & Google Cloud Run

### Backend on Cloud Run
```bash
# Deploy FastAPI backend to Cloud Run
gcloud run deploy sinhala-tamil-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY="YOUR_KEY"
```

### Frontend on Firebase Hosting
```bash
# Build frontend with Cloud Run WebSocket URL
cd frontend
VITE_WS_URL="wss://sinhala-tamil-backend-xyz-uc.a.run.app" npm run build
cd ..

# Deploy to Firebase Hosting
firebase deploy --only hosting
```

---

## 4. ▲ Vercel Deployment (Frontend)

1. Import GitHub repository in [Vercel](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. Add Environment Variable:
   - `VITE_WS_URL`: `wss://your-backend-domain.com`
4. Click **Deploy**.
