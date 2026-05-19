# Implements PHASE_6_SPEC.md §6.1 — three service accounts + GCS signer.

resource "google_service_account" "api" {
  account_id   = "solvo-onramp-api"
  display_name = "Solvo Onramp — FastAPI"
}

resource "google_service_account" "worker" {
  account_id   = "solvo-onramp-worker"
  display_name = "Solvo Onramp — Celery worker"
}

resource "google_service_account" "dispatcher" {
  account_id   = "solvo-onramp-dispatcher"
  display_name = "Solvo Onramp — Outbox dispatcher / beat"
}

resource "google_service_account" "gcs_signer" {
  account_id   = "solvo-onramp-signer"
  display_name = "Solvo Onramp — GCS V4 URL signer"
}

# Common IAM bindings.
locals {
  api_roles = [
    "roles/cloudsql.client",
    "roles/redis.editor",
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectViewer",
    "roles/iam.serviceAccountTokenCreator",
  ]
  worker_roles = [
    "roles/cloudsql.client",
    "roles/redis.editor",
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
  ]
  dispatcher_roles = [
    "roles/cloudsql.client",
    "roles/redis.editor",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
  ]
}

resource "google_project_iam_member" "api_bindings" {
  for_each = toset(local.api_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "worker_bindings" {
  for_each = toset(local.worker_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "dispatcher_bindings" {
  for_each = toset(local.dispatcher_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.dispatcher.email}"
}

# Allow api SA to impersonate the signer SA for V4 signed URLs.
resource "google_service_account_iam_member" "api_can_sign" {
  service_account_id = google_service_account.gcs_signer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.api.email}"
}
