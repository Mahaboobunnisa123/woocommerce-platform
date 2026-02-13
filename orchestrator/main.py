# main.py
import os
import uuid
import json
import subprocess
import logging
import secrets
from typing import List, Dict, Any, Tuple, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orchestrator")
app = FastAPI(title="WooCommerce Store Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Paths (absolute, deterministic, independent of current working dir) ---
def _init_paths() -> Tuple[str, str, str, str, str]:
    """
    Initialize and validate all paths. Returns (repo_root, chart_path, values_local, values_prod).
    This is called at startup and cached to ensure deterministic behavior.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))  # orchestrator/
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))  # repo root
    chart_path = os.path.join(repo_root, "helm", "woocommerce")
    values_local = os.path.join(repo_root, "values-local.yaml")
    values_prod = os.path.join(repo_root, "values-prod.yaml")
    
    # Validate critical paths exist
    if not os.path.isdir(repo_root):
        raise RuntimeError(f"Repository root not found: {repo_root}")
    if not os.path.isdir(chart_path):
        raise RuntimeError(f"Helm chart directory not found: {chart_path}")
    if not os.path.isfile(values_local):
        raise RuntimeError(f"values-local.yaml not found: {values_local}")
    if not os.path.isfile(values_prod):
        raise RuntimeError(f"values-prod.yaml not found: {values_prod}")
    
    return repo_root, chart_path, values_local, values_prod

REPO_ROOT, CHART_PATH, VALUES_LOCAL, VALUES_PROD = _init_paths()

# --- API models ---
class StoreRequest(BaseModel):
    store_name: str
    domain: str
    environment: str = "local"  # "local" or "prod"

class StoreResponse(BaseModel):
    id: str
    store_name: str
    namespace: str
    domain: str
    status: str
    helm_release: str
    created_at: str | None = None


# In-memory tracking (replace with DB for production)
stores: Dict[str, Dict[str, Any]] = {}

# helpers 
def run_command(cmd: List[str], cwd: Optional[str] = None, timeout: int = 600) -> Tuple[int, str, str]:
    """
    Run a subprocess command (list form). Return (returncode, stdout, stderr).
    """
    log.debug("RUN CMD: %s (cwd=%s)", " ".join(cmd), cwd or "")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        log.debug("RC=%s stdout=%s stderr=%s", proc.returncode, stdout[:200], stderr[:200])
        return proc.returncode, stdout, stderr
    except Exception as e:
        log.exception("Command execution failed")
        return 254, "", str(e)

def ingress_host_exists(host: str) -> Optional[Dict[str, str]]:
    """
    Return {'namespace': ns, 'ingress': name} if host already used by any ingress (-A).
    If kubectl fails for any reason, return None (we can't check conservatively).
    """
    rc, out, err = run_command(["kubectl", "get", "ingress", "-A", "-o", "json"])
    if rc != 0 or not out:
        log.warning("Could not list ingresses: rc=%s err=%s", rc, err[:200])
        return None
    try:
        payload = json.loads(out)
    except Exception:
        log.exception("Failed to parse kubectl ingress JSON")
        return None
    for item in payload.get("items", []):
        ns = item.get("metadata", {}).get("namespace", "")
        name = item.get("metadata", {}).get("name", "")
        rules = item.get("spec", {}).get("rules", []) or []
        for r in rules:
            if r.get("host") == host:
                return {"namespace": ns, "ingress": name}
    return None

# --- endpoints ---
@app.post("/stores", response_model=StoreResponse)
async def create_store(req: StoreRequest):
    store_name = req.store_name.strip().lower()
    domain = req.domain.strip()
    env = req.environment.strip().lower()
    if not store_name or not domain:
        raise HTTPException(status_code=400, detail="store_name and domain are required")

    # unique ID to avoid naming collisions
    store_id = str(uuid.uuid4())[:8]
    namespace = f"{store_name}-{store_id}"
    release = f"{store_name}-{store_id}"
    created_at = datetime.now(timezone.utc).isoformat()
    stores[store_id] = {
        "id": store_id,
        "store_name": store_name,
        "namespace": namespace,
        "domain": domain,
        "status": "Provisioning",
        "helm_release": release,
        "environment": env,
        "created_at": created_at
    }
    log.info(f"STORE_CREATE id={store_id} name={store_name} namespace={namespace} release={release} domain={domain}")

    # Prevent shared-host ingress collisions by checking if any existing ingress already uses the requested domain.
    conflict = ingress_host_exists(domain)
    if conflict:
        stores[store_id]["status"] = "Failed"
        detail = f"ingress host conflict: host '{domain}' already used in {conflict['namespace']}/{conflict['ingress']}"
        log.error(detail)
        raise HTTPException(status_code=409, detail=detail)

    # 1) create namespace (idempotent)
    rc, out, err = run_command(["kubectl", "create", "namespace", namespace])
    if rc != 0 and "already exists" not in (err or out).lower():
        stores[store_id]["status"] = "Failed"
        raise HTTPException(status_code=500, detail=f"Namespace creation failed: {err or out}")

    # 2) create DB secret (idempotent)
    secret_name = f"{namespace}-db-secret"
    root_password = secrets.token_urlsafe(16)
    user_password = secrets.token_urlsafe(16)

    rc, out, err = run_command([
       "kubectl", "create", "secret", "generic", secret_name,
      f"--from-literal=root-password={root_password}",
      f"--from-literal=user-password={user_password}",
      f"--namespace={namespace}"
   ])
    if rc != 0 and "already exists" not in (err or out).lower():
        stores[store_id]["status"] = "Failed"
        raise HTTPException(status_code=500, detail=f"Secret creation failed: {err or out}")

    # 3) choose values file (already validated at startup, guaranteed to exist)
    values_file = VALUES_LOCAL if env == "local" else VALUES_PROD
    log.debug("Using values file: %s", values_file)

    # 4) helm install (wait for readiness)
    helm_cmd = [
        "helm", "install", release, CHART_PATH,
        "--namespace", namespace,
        "--values", values_file,
        "--set", f"ingress.host={domain}",
        "--set", f"storeName={namespace}",
        "--wait",
        "--timeout", "10m"
    ]
    rc, out, err = run_command(helm_cmd, cwd=REPO_ROOT, timeout=600)
    if rc != 0:
        # cleanup partially-created resources
        log.error("Helm install failed: %s", (err or out)[:1000])
        run_command(["helm", "uninstall", release, "-n", namespace])
        run_command(["kubectl", "delete", "namespace", namespace])
        stores[store_id]["status"] = "Failed"
        raise HTTPException(status_code=500, detail=f"helm install failed: {(err or out)[:1000]}")

    # success
    stores[store_id]["status"] = "Ready"
    log.info("Provisioned store %s -> namespace=%s", store_name, namespace)
    return StoreResponse(**stores[store_id])

@app.get("/stores", response_model=List[StoreResponse])
async def list_stores():
    return [StoreResponse(**s) for s in stores.values()]

@app.delete("/stores/{store_id}")
async def delete_store(store_id: str):
    if store_id not in stores:
        raise HTTPException(status_code=404, detail="Store not found")
    meta = stores[store_id]
    namespace = meta["namespace"]
    release = meta["helm_release"]
    log.info(f"DELETE_REQUEST id={store_id} namespace={namespace}")
    rc, out, err = run_command(["helm", "uninstall", release, "-n", namespace])
    log.info(f"STORE_DELETE id={store_id} namespace={namespace}")
    rc2, out2, err2 = run_command(["kubectl", "delete", "namespace", namespace])
    del stores[store_id]
    if rc != 0:
        return {"status": "uninstall-error", "helm_err": (err or out)[:1000], "kubectl": {"rc": rc2, "out": out2[:1000], "err": err2[:1000]}}
    return {"status": "deleted", "release": release, "namespace": namespace}

@app.get("/")
async def root():
    return {
        "message": "orchestrator up",
        "repo_root": REPO_ROOT,
        "chart_path": CHART_PATH,
        "values_local": VALUES_LOCAL,
        "values_prod": VALUES_PROD
    }
    
if __name__ == "__main__":
    import uvicorn
    log.info("Starting orchestrator")
    log.info("  Repository Root:    %s", REPO_ROOT)
    log.info("  Chart Path:         %s", CHART_PATH)
    log.info("  Values (local):     %s", VALUES_LOCAL)
    log.info("  Values (prod):      %s", VALUES_PROD)
    log.info("All required files and directories validated at startup ✓")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
