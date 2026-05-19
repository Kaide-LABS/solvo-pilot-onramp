# Implements PHASE_6_SPEC.md §6.1 — Memorystore Redis 7.4.

resource "google_redis_instance" "cache" {
  name           = "solvo-onramp-cache"
  region         = var.region
  tier           = "STANDARD_HA"
  memory_size_gb = 1
  redis_version  = "REDIS_7_4"

  authorized_network = google_compute_network.vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  read_replicas_mode = "READ_REPLICAS_DISABLED"
}
