# Implements PHASE_6_SPEC.md §6.1 — single VPC + Serverless VPC Access connector.

resource "google_compute_network" "vpc" {
  name                    = "solvo-onramp-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "solvo-onramp-subnet"
  ip_cidr_range = "10.20.0.0/20"
  region        = var.region
  network       = google_compute_network.vpc.id
}

resource "google_vpc_access_connector" "connector" {
  name           = "solvo-onramp-conn"
  region         = var.region
  ip_cidr_range  = "10.21.0.0/28"
  network        = google_compute_network.vpc.name
  min_throughput = 200
  max_throughput = 300
}
