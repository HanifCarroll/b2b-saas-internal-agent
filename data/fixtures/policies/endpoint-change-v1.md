---
id: endpoint-change-v1
title: Endpoint change policy
version: 1
owner: Implementation Operations
access: shared_internal
status: superseded
effective_on: 2026-01-01
superseded_on: 2026-09-01
superseded_by: endpoint-change-v2
---

# Endpoint change policy — version 1

Archived for historical reference. Version 2 replaces this policy from September 1, 2026.

Implementation engineers may change webhook endpoints for customers assigned to them after confirming an authorized customer request and a registered destination. Production changes must occur within the customer's approved change window.

The engineer preparing a production change may approve it themselves. Record the approval before execution.

After changing the endpoint, verify the active configuration and delivery of a test event. Record the outcome in the change register and support ticket. Escalate an unsuccessful or uncertain result.
