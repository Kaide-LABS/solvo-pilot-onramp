# Implements PHASE_6_SPEC.md §6.1 — Cloud SQL Postgres 17.

resource "google_sql_database_instance" "pg" {
  name             = "solvo-onramp-pg"
  database_version = "POSTGRES_17"
  region           = var.region

  settings {
    tier              = "db-custom-1-3840"
    availability_type = "ZONAL"
    disk_size         = 20
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled    = true
      start_time = "01:00"
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "onramp" {
  name     = "onramp"
  instance = google_sql_database_instance.pg.name
}

resource "random_password" "pg_password" {
  length  = 32
  special = true
}

resource "google_sql_user" "onramp_user" {
  name     = "onramp"
  instance = google_sql_database_instance.pg.name
  password = random_password.pg_password.result
}
