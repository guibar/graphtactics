output "artifact_registry_repo" {
  description = "The URL of the Artifact Registry repository"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_name}"
}

output "backend_url" {
  description = "The URL of the backend service"
  value       = google_cloud_run_service.backend.status[0].url
}

output "frontend_url" {
  description = "The URL of the frontend service"
  value       = google_cloud_run_service.frontend.status[0].url
}
