# Implements PHASE_6_SPEC.md §6.1 — three Cloud Run services.

locals {
  artifact_registry = "europe-west4-docker.pkg.dev/${var.project_id}/solvo"
  postgres_dsn_async = "postgresql+asyncpg://onramp@/onramp?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"
  postgres_dsn_sync  = "postgresql+psycopg2://onramp@/onramp?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"
  redis_url          = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"

  common_env = {
    ENVIRONMENT             = "production"
    GCP_PROJECT_ID          = var.project_id
    VERTEX_LOCATION         = var.region
    POSTGRES_DSN_ASYNC      = local.postgres_dsn_async
    POSTGRES_DSN_SYNC       = local.postgres_dsn_sync
    REDIS_URL               = local.redis_url
    GCS_BUCKET_OUTPUTS      = google_storage_bucket.outputs.name
    GCS_ARCHIVE_BUCKET      = google_storage_bucket.archive.name
    GCS_SIGNER_SERVICE_ACCOUNT = google_service_account.gcs_signer.email
    VERTEX_AI_ZDR_ENROLLED  = var.vertex_ai_zdr_enrolled ? "true" : "false"
  }
}

resource "google_cloud_run_v2_service" "api" {
  name     = "solvo-onramp-api"
  location = var.region

  template {
    service_account = google_service_account.api.email

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "${local.artifact_registry}/api:${var.release_tag}"

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "SLACK_SIGNING_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.slack_signing_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SLACK_BOT_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.slack_bot_token.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "INTERNAL_ADMIN_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.internal_admin_token.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get { path = "/v1/health/ready" }
        initial_delay_seconds = 20
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get { path = "/v1/health/ready/cloudrun" }
        timeout_seconds   = 3
        period_seconds    = 15
        failure_threshold = 3
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "solvo-onramp-worker"
  location = var.region

  template {
    service_account = google_service_account.worker.email

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 3
    }

    containers {
      image = "${local.artifact_registry}/worker:${var.release_tag}"

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "dispatcher" {
  name     = "solvo-onramp-dispatcher-beat"
  location = var.region

  template {
    service_account = google_service_account.dispatcher.email

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    containers {
      image = "${local.artifact_registry}/dispatcher:${var.release_tag}"

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}
