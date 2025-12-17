#!/bin/bash
set -e

# Project-specific values
gcp_project_id="graphtactics"
gcp_region="europe-west1"
backend_service_name="graphtactics-backend"
frontend_service_name="graphtactics-frontend"
repository_name="graphtactics-repo"

# Generate a unique tag for this deployment
TAG=$(date +%Y%m%d%H%M%S)
echo "Deploying with tag: $TAG"

# 1. Build Docker images
echo "Building backend Docker image..."
docker build -t ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/backend:latest \
             -t ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/backend:$TAG ./backend

echo "Building frontend Docker image..."
docker build -t ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/frontend:latest \
             -t ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/frontend:$TAG ./frontend

# 2. Authenticate with Google Cloud (ensure gcloud is installed and configured)
echo "Authenticating with Google Cloud..."
gcloud auth configure-docker ${gcp_region}-docker.pkg.dev

echo "Setting GCP project..."
gcloud config set project ${gcp_project_id}

# 3. Push images to Artifact Registry
echo "Pushing backend image..."
docker push ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/backend:latest
docker push ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/backend:$TAG

echo "Pushing frontend image..."
docker push ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/frontend:latest
docker push ${gcp_region}-docker.pkg.dev/${gcp_project_id}/${repository_name}/frontend:$TAG

# 4. Deploy infrastructure with Terraform
echo "Deploying infrastructure with Terraform..."
cd ./terraform
terraform init
terraform apply -auto-approve \
  -var="image_tag=$TAG" \
  -var="project_id=$gcp_project_id" \
  -var="region=$gcp_region" \
  -var="backend_service_name=$backend_service_name" \
  -var="frontend_service_name=$frontend_service_name" \
  -var="repository_name=$repository_name"


echo "Deployment complete!"
