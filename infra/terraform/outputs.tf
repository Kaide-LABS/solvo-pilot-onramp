# Implements PHASE_6_SPEC.md §6.1 — terraform outputs.

output "cloud_run_api_url" {
  value       = google_cloud_run_v2_service.api.uri
  description = "Public HTTPS URL for the API service (auth required)."
}

output "cloud_run_worker_url" {
  value       = google_cloud_run_v2_service.worker.uri
  description = "Cloud Run URL of the worker service."
}

output "cloud_run_dispatcher_url" {
  value       = google_cloud_run_v2_service.dispatcher.uri
  description = "Cloud Run URL of the dispatcher-beat service."
}

output "cloud_sql_connection_name" {
  value       = google_sql_database_instance.pg.connection_name
  description = "Cloud SQL instance connection name (project:region:instance)."
}

output "gcs_outputs_bucket" {
  value = google_storage_bucket.outputs.name
}

output "gcs_archive_bucket" {
  value = google_storage_bucket.archive.name
}
