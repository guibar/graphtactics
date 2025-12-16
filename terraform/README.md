# GraphTactics Terraform Deployment

This directory contains the Terraform configuration to deploy GraphTactics to Google Cloud Run.

## Prerequisites

1. [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and authenticated (`gcloud auth login`).
2. [Terraform](https://www.terraform.io/downloads.html) installed.
3. A Google Cloud Project.

## Setup

1. Copy `terraform.tfvars.example` to `terraform.tfvars`:

    ```bash
    cp terraform.tfvars.example terraform.tfvars
    ```

2. Edit `terraform.tfvars` and set your `project_id`.

## Deployment Steps

### 1. Initialize and Create Repository

First, we need to create the Artifact Registry repository so we can push our Docker images.

```bash
terraform init
terraform apply -target=google_artifact_registry_repository.repo
```

### 2. Build and Push Images

Use the repository URL output from the previous step to tag and push your images.

```bash
# Get the repo URL
REPO=$(terraform output -raw artifact_registry_repo)

# Build and Push Backend
docker build -t $REPO/backend:latest ../backend
docker push $REPO/backend:latest

# Build and Push Frontend
# Note: The frontend image doesn't need the backend URL at build time anymore!
docker build -t $REPO/frontend:latest ../frontend
docker push $REPO/frontend:latest
```

### 3. Deploy Services

Now that the images are in the registry, deploy the Cloud Run services.

```bash
terraform apply
```

Terraform will automatically:

1. Deploy the Backend service.
2. Get the Backend URL.
3. Deploy the Frontend service with the `BACKEND_URL` environment variable set to the Backend's URL.

## Access

After `terraform apply` completes, it will output the `frontend_url`. Open this URL in your browser.
