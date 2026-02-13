<div align="center">
  
# WooCommerce Multi-Tenant Provisioning Platform
Kubernetes-native multi-tenant WooCommerce provisioning platform built with Helm, FastAPI, React, and production-aware
<p align="center">
  <img src="assets/image.png" width="100%" alt="GitHub Banner"/>
</p>

![Kubernetes](https://img.shields.io/badge/Kubernetes-Orchestrated-326CE5?logo=kubernetes&logoColor=white)
![Helm](https://img.shields.io/badge/Helm-Chart%20Driven-0F1689?logo=helm&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Dashboard-61DAFB?logo=react&logoColor=black)
![MariaDB](https://img.shields.io/badge/MariaDB-Stateful-003545?logo=mariadb&logoColor=white)
<br/>

![Multi-Tenant](https://img.shields.io/badge/Multi--Tenant-Namespace%20Isolation-orange)
![ResourceQuota](https://img.shields.io/badge/K8s-ResourceQuota-success)
![LimitRange](https://img.shields.io/badge/K8s-LimitRange-blueviolet)
![Persistent Storage](https://img.shields.io/badge/PVC-Persistent%20Storage-critical)
![Ingress](https://img.shields.io/badge/Ingress-NGINX-1f425f)
<br/>

![k3s-ready (config)](https://img.shields.io/badge/Deployment-k3s%20config-brightgreen)
![Infrastructure as Code](https://img.shields.io/badge/IaC-Helm%20Based-ff69b4)
![Cloud Native](https://img.shields.io/badge/Architecture-Cloud%20Native-blue)
</div>

## Repo Structure
```
woocommerce-platform/
├── dashboard/                # React app (localhost:3000)
├── orchestrator/             # FastAPI app (localhost:8000)
│   └── main.py
├── helm/woocommerce/         # Helm chart
│   └── templates/
│       ├── deployment.yaml
│       ├── statefulset.yaml  # uses 'volumeClaimTemplates' (PVCs autocreated by the StatefulSet)
│       ├── service.yaml
│       ├── ingress.yaml
│       ├── resourcequota.yaml      
│       └── limitrange.yaml         
├── values-local.yaml
├── values-prod.yaml
├── SYSTEM_DESIGN.md
└── README.md
```
## Quick links (files in repo)
- `helm/woocommerce/` — Helm chart (templates for Deployment, StatefulSet, Services, Ingress, ResourceQuota, LimitRange)
- `values-local.yaml`, `values-prod.yaml` — Environment overrides (local vs prod)
- `orchestrator/main.py` — FastAPI orchestrator (creates namespaces, secrets, runs `helm install`, waits)
- `dashboard/` — React frontend (create / list / delete stores)
- `SYSTEM_DESIGN.md` — Short system design & tradeoffs (architecture rationale and production checklist)
- `README.md` — (this file)


## Local setup (Docker Desktop / Minikube / kind / k3d)
### 1) Prerequisites
- Docker Desktop (or Minikube / kind / k3d)
- kubectl (configured to your cluster)
- Helm 3.x
- Node.js (16+) and npm (for dashboard)
- Python 3.9+ and `pip` (for orchestrator)

### 2) Install an ingress controller (required for host routing)
For Docker Desktop / kind / k3d you can use the nginx ingress controller:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
```

Verify the ingress controller is running:
```bash
kubectl get pods -n ingress-nginx
```

### 3) Map local hostnames (one-time)
Add host entries so your browser resolves each store domain to localhost (Windows: `C:\Windows\System32\drivers\etc\hosts`):
```
127.0.0.1 localhost
127.0.0.1 store.localhost
127.0.0.1 demo.localhost
# Add a line per store domain you plan to create
```
> Note: For the demo, either (A) edit `/etc/hosts` for each store domain, or (B) use a wildcard/automation script to add `<uuid>.localhost` entries before creating stores.

### 4) Start dashboard
```bash
cd dashboard
npm install
npm start
# Open http://localhost:3000
```

### 5) Start orchestrator
```bash
cd orchestrator
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
pip install -r requirements.txt
python main.py
# API: http://localhost:8000
```
You can confirm orchestrator is up by visiting `http://localhost:8000/`

### 6) Create a store (via UI or API)
Use the dashboard UI or curl:

```bash
curl -X POST http://localhost:8000/stores \
  -H "Content-Type: application/json" \
  -d '{"store_name":"demo","domain":"demo.localhost","environment":"local"}'
```

The orchestrator will:
- create a unique namespace `demo-<8char-id>`
- generate DB secrets and store them in K8s
- run `helm install <release> ... --set ingress.host=demo.localhost --set storeName=<namespace>`
- wait for readiness and return `status: Ready` when done

### 7) Check progress (kubectl)
```bash
kubectl get namespaces | grep demo
kubectl get all -n <namespace>
kubectl get ingress -n <namespace>
kubectl get pvc -n <namespace>
kubectl describe pod -n <namespace> <pod-name>
```

### 8) Delete store (UI or API)
Dashboard Delete button or:
```bash
curl -X DELETE http://localhost:8000/stores/<store_id>
```
This triggers `helm uninstall` and `kubectl delete namespace <namespace>` as a cleanup path.

## Production-like VPS (k3s) deployment notes
This repository is structured so the same Helm chart can be deployed on both local Kubernetes clusters (Kind / Minikube / k3d) and production-like environments such as k3s using environment-specific values files.

### Key differences to set for production
- storage class (use durable storage, not hostPath)
- ingress host (real domain) and TLS (cert-manager)
- increased resource requests & limits
- RBAC service account for orchestrator (least privilege)
- secret backend (Vault / SealedSecrets) instead of plain K8s secrets stored manually

### Example k3s steps (high-level)
1. Provision VPS (Ubuntu 20.04+), open ports 80/443 and 22.
2. Install k3s: `curl -sfL https://get.k3s.io | sh -` (or follow k3s docs).
3. Install an ingress controller (k3s includes a default one or you can install nginx/traefik).
4. Ensure storage class (e.g., `local-path`) exists for PVCs.
5. Update `values-prod.yaml` with your domain and storageClassName values.
6. Deploy orchestrator & dashboard (optionally containerize them and deploy into k3s):
   ```bash
   # example helm usage to provision the first store:
   helm install woo-prod ./helm/woocommerce \
       --namespace woo-prod \
       --create-namespace \
       --values values-prod.yaml \
       --set ingress.host=store.example.com \
       --set storeName=woo-prod
   ```
7. Use cert-manager + Let's Encrypt for TLS in production (recommended).
> For a step-by-step VPS guide, consult `SYSTEM_DESIGN.md` (production checklist & caveats).

## How to create a store and place an order 
1. **Start prerequisites**: ingress controller, orchestrator (`python main.py`), dashboard (`npm start`), and ensure `/etc/hosts` entry exists for the store domain.  
2. **Create store (UI)**: Fill `Store Name = demo`, `Domain = demo.localhost`, environment = `local` → Click *Create*. UI shows status `Provisioning` → `Ready`.  
3. **Open storefront**: Click the domain shown in UI, e.g. `http://demo.localhost`. (If you hit the WordPress installer page, finish the WordPress setup: set site title, admin user/email/password. Then continue to the WP Admin.)  
4. **Install/complete WooCommerce plugin** (if setup wizard didn't preinstall it) — follow on-screen WooCommerce prompts. The demo can use default theme and products.  
5. **Add a product** (if not present): in WordPress admin (`http://demo.localhost/wp-admin`) → **Products → Add New** → set title, price, short description, publish.  
6. **Place an order** (storefront): visit the storefront (`http://demo.localhost`), find the product, **Add to Cart**, **Proceed to Checkout** → choose a test-friendly payment method (Cash on Delivery / COD or a dummy gateway) and complete the purchase.  
7. **Verify order**: In WordPress admin → **WooCommerce → Orders** → confirm the order appears. This demonstrates full end-to-end flow.  
8. **Delete store**: Back to the dashboard, click *Delete* (or `DELETE /stores/{id}`) and confirm the namespace and resources are cleaned up: `kubectl get ns | grep demo` should not show it.
Notes:
If WordPress shows the installer page, simply complete the one-time setup (site title, admin user/email/password) during the recording. For repeatable automation, a post-install Job (WP-CLI) can be used to pre-seed admin credentials — add this if you have time after the mandatory fixes.

## Security & hygiene 
What it includes:
- namespace-per-store isolation
- per-namespace ResourceQuota and LimitRange templates (to avoid cluster exhaustion)
- generated DB credentials stored as Kubernetes Secrets (created at provision time)
- DB credentials are generated at provision time using cryptographically random tokens (not hardcoded in source).

What you should add for production (recommended):
- orchestrator state persistence (Postgres) — currently stores state in memory (MVP)
- API authentication & rate-limiting (prevent abuse)
- RBAC (service account with least privilege) for orchestrator actions
- secret manager (Vault or SealedSecrets) for secure secret lifecycle
- certificates (cert-manager) and monitoring (Prometheus/Grafana) for observability

## Testing & troubleshooting quick commands
```bash
# List namespaces for created stores
kubectl get ns | grep store

# Check pods in a specific namespace
kubectl get pods -n <namespace>

# Describe a failing pod
kubectl describe pod <pod-name> -n <namespace>

# View logs for WordPress container
kubectl logs -l app=<release>-wordpress -n <namespace>

# View PVCs
kubectl get pvc -n <namespace>

# Delete a problematic namespace (careful)
kubectl delete namespace <namespace>
```
