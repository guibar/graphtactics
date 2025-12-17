variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
  default     = "graphtactics"
}

variable "region" {
  description = "The Google Cloud region to deploy to"
  type        = string
  default     = "europe-west1"
}

variable "backend_service_name" {
  description = "Name of the backend Cloud Run service"
  type        = string
  default     = "graphtactics-backend"
}

variable "frontend_service_name" {
  description = "Name of the frontend Cloud Run service"
  type        = string
  default     = "graphtactics-frontend"
}

variable "repository_name" {
  description = "Name of the Artifact Registry repository"
  type        = string
  default     = "graphtactics-repo"
}

variable "image_tag" {
  description = "The tag of the Docker image to deploy"
  type        = string
  default     = "latest"
}
