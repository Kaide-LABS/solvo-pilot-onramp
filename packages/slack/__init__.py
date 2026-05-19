"""Slack adapter — signing, Block Kit, handlers. See PHASE_5_SPEC.md §1.

ALL Slack outbound calls flow through the transactional outbox dispatcher;
the modules here never POST to Slack directly from a request handler.
"""
