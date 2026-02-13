# System Design & Tradeoffs

## 1. Architecture Overview
### High-Level Components

-   **React Dashboard (Port 3000)**\
    Provides UI for creating, listing, and deleting stores.

-   **FastAPI Orchestrator (Port 8000)**\
    Handles provisioning logic, Helm execution, namespace management,
    and lifecycle tracking.

-   **Kubernetes Cluster (Local / k3s-ready)**\
    Each store runs inside its own namespace with:

    -   WordPress Deployment
    -   MariaDB StatefulSet
    -   Services (ClusterIP)
    -   Ingress
    -   PersistentVolumeClaim
    -   ResourceQuota
    -   LimitRange
    -   Secret (DB credentials)

### Architecture Diagram
Dashboard → Orchestrator → Helm → Kubernetes\
Each Store → Dedicated Namespace → Isolated Resources

This design ensures multi-tenant isolation with namespace-per-store
boundaries.

## 2. Architecture Choices & Tradeoffs

### Namespace-per-Store Isolation

**Chosen:** Yes
**Why:**\
- Strong isolation boundary\
- Clean teardown (delete namespace removes everything)\
- Enables per-store quotas\
- Simplifies blast-radius control

**Tradeoff:**\
- Higher Kubernetes API usage\
- More namespaces to manage

### Helm-based Provisioning (Not Raw YAML)

**Chosen:** Yes

**Why:**\
- Environment separation via values files\
- Reproducible deployments\
- Upgrade and rollback support

**Tradeoff:**\
- Requires Helm binary\
- Slightly more complexity than plain kubectl

### External Orchestrator (FastAPI)

**Chosen:** Yes

**Why:**\
- Simple control plane\
- Easy to reason about\
- Easy to demo

**Tradeoff:**\
- Not a Kubernetes Operator\
- Single instance unless containerized and scaled

## 3. Idempotency, Failure Handling & Cleanup

### Namespace Creation

-   `kubectl create namespace`
-   Safe if retried (already-exists handled)

### Secret Creation

-   Generated using `secrets.token_urlsafe()`
-   No hardcoded credentials
-   Already-exists handled safely

### Helm Install

-   Uses `--wait --timeout`
-   If Helm fails:
    -   Helm uninstall executed
    -   Namespace deleted
    -   Store marked as Failed

### Cleanup Guarantee

Delete flow: 1. `helm uninstall` 2. `kubectl delete namespace` 3. Remove
from in-memory store registry
Namespace deletion ensures full garbage collection of: - Pods -
Services - Ingress - PVC - Secrets

## 4. Created Timestamp (User Story Compliance)

Each store includes a `created_at` timestamp.
Example (API response):

``` json
{
  "id": "a1b2c3d4",
  "store_name": "demo",
  "namespace": "demo-a1b2c3d4",
  "domain": "demo.localhost",
  "status": "Ready",
  "helm_release": "demo-a1b2c3d4",
  "created_at": "2026-02-13T10:30:00Z"
}
```
This enables: - Dashboard visibility - Audit reference - Lifecycle
tracking

## 5. Resource Guardrails (Multi-Tenant Protection)

Each namespace includes:

### ResourceQuota

Limits: - CPU - Memory - Pod count

Prevents one store exhausting cluster capacity.

### LimitRange

Defines default: - CPU requests - Memory requests

Ensures pods always declare resources.
This satisfies multi-tenant isolation guardrails.

## 6. Persistent Storage Design

MariaDB uses a StatefulSet with volumeClaimTemplates.
### PVC Behavior

-   Created automatically per store
-   Bound to cluster storage class
-   Persistent across pod restarts

### Reclaim Policy Consideration

PVC lifecycle depends on StorageClass reclaim policy.
Typical local behavior: - `Delete` policy → PV removed when PVC
deleted - Namespace deletion removes PVC

In production: - Reclaim policy must be validated carefully to avoid
orphaned volumes.

## 7. Minimal Reconciliation Behavior

Current system handles: - Helm failure cleanup - Namespace idempotency
checks

However:

Full reconciliation loop is not implemented.\
If orchestrator crashes mid-provisioning, manual cleanup may be
required.

Future improvement: - Store lifecycle state machine - Reconciliation on
startup - Persistent database for store tracking

## 8. What Changes for Production

### DNS

Local: - /etc/hosts mapping

Production: - Real DNS (example.com) - Ingress host set via
values-prod.yaml

### Ingress

Local: - NGINX Ingress Controller - HTTP only

Production: - TLS (cert-manager recommended) - HTTPS termination -
Public load balancer

### Storage Class

Local: - hostpath (Docker Desktop)

Production (k3s): - local-path or cloud storage class

### Secrets

Current: - Kubernetes Secret per namespace

Production Improvements: - Sealed Secrets or external secret manager -
RBAC restriction on secret access

## 9. Scalability Plan

### Dashboard

Stateless → Horizontally scalable

### Orchestrator
Currently single instance\

To scale: - Containerize into Kubernetes - Add persistent database - Add
job queue for parallel provisioning

### WordPress
Can scale replicas (read scaling)

### MariaDB
Single replica (stateful)\

Horizontal DB scaling requires different architecture.

## 10. Summary
This design prioritizes:

-   Clear isolation (namespace-per-store)
-   Deterministic cleanup
-   Helm-based reproducibility
-   Resource guardrails
-   Secret safety (no hardcoded secrets)
-   Persistent database storage
-   Timestamp lifecycle tracking

The system runs locally and is production-adaptable via Helm values.

Production hardening requires: - Authentication - Rate limiting - TLS -
Persistent orchestrator state - Monitoring and observability

**Status:** Production-adaptable MVP with isolation, persistence, and
lifecycle guarantees.
