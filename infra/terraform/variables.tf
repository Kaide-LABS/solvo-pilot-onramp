# Implements PHASE_6_SPEC.md §6.1.

variable "project_id" {
  description = "GCP project ID for the Solvo Pilot Onramp pilot deployment."
  type        = string
}

variable "region" {
  description = "Locked to europe-west4 per ULTIMATE_PRD §3.2."
  type        = string
  default     = "europe-west4"
  validation {
    condition     = var.region == "europe-west4"
    error_message = "Region is locked to europe-west4 per ULTIMATE_PRD §3.2."
  }
}

variable "release_tag" {
  description = "Image tag (short SHA) to deploy."
  type        = string
  default     = "latest"
}

variable "vertex_ai_zdr_enrolled" {
  description = "Set true only after the GCP organization has been enrolled in the Vertex AI Zero Data Retention program (per docs/compliance_setup.md)."
  type        = bool
  default     = false
}
