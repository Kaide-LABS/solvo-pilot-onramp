"""Transactional outbox dispatcher. See PHASE_5_SPEC.md §6.4.

The dispatcher is the ONLY place in the project that hits external systems
(Slack, GCS, webhooks). Request handlers write outbox rows; the dispatcher
drains them.
"""
