# Implements PHASE_6_SPEC.md §6.1 — GCS buckets + §3.10.3 retention windows.

resource "google_storage_bucket" "outputs" {
  name                        = "solvo-onramp-outputs-${var.project_id}"
  location                    = "EU"
  uniform_bucket_level_access = true
  storage_class               = "STANDARD"

  # Raw uploads: 7-day TTL (§3.10.3 floor).
  lifecycle_rule {
    condition {
      age            = 7
      matches_prefix = ["raw/"]
    }
    action {
      type = "Delete"
    }
  }

  # Normalized outputs in this bucket: nothing — they live in Postgres until
  # the 90-day archive job moves them to the archive bucket below.

  versioning {
    enabled = false
  }
}

resource "google_storage_bucket" "archive" {
  name                        = "solvo-onramp-archive-${var.project_id}"
  location                    = "EU"
  uniform_bucket_level_access = true
  storage_class               = "COLDLINE"

  # 180-day retention floor on archived normalized outputs (§3.10.3).
  lifecycle_rule {
    condition {
      age            = 180
      matches_prefix = ["jobs/"]
    }
    action {
      type = "Delete"
    }
  }
}
