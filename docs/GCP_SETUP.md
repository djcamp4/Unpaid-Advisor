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

# OpenRouter API key (get from https://openrouter.ai/keys)
echo -n "YOUR_OPENROUTER_API_KEY" | \
  gcloud secrets create openrouter-api-key --data-file=-
```

### 4. Grant Cloud Run access to secrets
The Cloud Run service identity needs permission to read Secret Manager secrets at runtime:
```bash
# Default Cloud Run service account format: PROJECT_NUMBER-compute@developer.gserviceaccount.com
# Find your project number:
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 5. GitHub Actions — Workload Identity Federation
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

### 6. Add GitHub Actions secrets
In your repo Settings → Secrets → Actions, add:
- `GCP_PROJECT_ID` — your GCP project ID
- `GCP_WORKLOAD_IDENTITY_PROVIDER` — from step 5 output
- `GCP_SERVICE_ACCOUNT` — `github-actions@PROJECT_ID.iam.gserviceaccount.com`

## Local development

### Backend
```bash
cd backend
pip install -r requirements.txt
OPENROUTER_API_KEY=your_key uvicorn main:app --reload --port 8080
```
The `OPENROUTER_API_KEY` env var enables the AI summary. Without it the summary field is omitted gracefully.

### Frontend
```bash
cd frontend
npm install
npm run dev   # proxies /analyze → localhost:8080
```

## Updating the Firebase project name
Edit `.firebaserc` and replace `"unpaid-advisor"` with your actual Firebase project ID.
