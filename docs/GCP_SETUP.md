# GCP Setup Guide

## Prerequisites
- Google Cloud project created
- Firebase project linked to same GCP project
- `gcloud` CLI installed locally

## One-time GCP setup

### 1. Enable APIs
```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

### 2. Create Artifact Registry repository
```bash
gcloud artifacts repositories create unpaid-advisor \
  --repository-format=docker \
  --location=us-central1
```

### 3. Store secrets in Secret Manager
```bash
# Firebase CI token (run: firebase login:ci)
echo -n "YOUR_FIREBASE_CI_TOKEN" | \
  gcloud secrets create firebase-token --data-file=-

# Backend API URL (set after first Cloud Run deploy)
echo -n "https://YOUR-CLOUD-RUN-URL" | \
  gcloud secrets create vite-api-url --data-file=-
```

### 4. GitHub Actions — Workload Identity Federation
```bash
# Create service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions"

# Grant roles
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:github-actions@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:github-actions@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:github-actions@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Create workload identity pool
gcloud iam workload-identity-pools create github \
  --location=global \
  --display-name="GitHub Actions Pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"
```

### 5. Add GitHub Actions secrets
In your repo Settings → Secrets → Actions, add:
- `GCP_PROJECT_ID` — your GCP project ID
- `GCP_WORKLOAD_IDENTITY_PROVIDER` — from step 4 output
- `GCP_SERVICE_ACCOUNT` — `github-actions@PROJECT_ID.iam.gserviceaccount.com`

## Local development

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev   # proxies /analyze → localhost:8080
```

## Updating the Firebase project name
Edit `.firebaserc` and replace `"unpaid-advisor"` with your actual Firebase project ID.
