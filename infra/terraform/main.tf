# Implements PHASE_6_SPEC.md §6.1. Provider + project pin.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0, < 7"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
