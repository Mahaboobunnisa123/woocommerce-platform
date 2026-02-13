import React, { useEffect, useState } from "react";
import "./App.css";

function App() {
  const [stores, setStores] = useState([]);
  const [storeName, setStoreName] = useState("");
  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const API_ROOT = "http://localhost:8000";

  const fetchStores = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_ROOT}/stores`);
      const data = await response.json();
      setStores(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Failed to fetch stores", err);
      setStores([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStores();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createStore = async () => {
    if (!storeName.trim() || !domain.trim()) {
      alert("Store name and domain are required.");
      return;
    }
    setCreating(true);
    try {
      await fetch(`${API_ROOT}/stores`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          store_name: storeName,
          domain: domain,
          environment: "local",
        }),
      });
      setStoreName("");
      setDomain("");
      await fetchStores();
    } catch (err) {
      console.error("Create failed", err);
      alert("Failed to create store. See console.");
    } finally {
      setCreating(false);
    }
  };

  const deleteStore = async (id, storeDomain) => {
    if (!window.confirm(`Delete this store and all resources?\n\n${storeDomain}`)) return;
    try {
      await fetch(`${API_ROOT}/stores/${id}`, { method: "DELETE" });
      await fetchStores();
    } catch (err) {
      console.error("Delete failed", err);
      alert("Failed to delete store. See console.");
    }
  };

  const domainUrl = (d) => {
    if (!d) return "#";
    if (d.startsWith("http://") || d.startsWith("https://")) return d;
    return `http://${d}`;
  };

  const statusClass = (status) => {
    if (!status) return "status-unknown";
    const s = status.toLowerCase();
    if (s.includes("ready")) return "status-ready";
    if (s.includes("provision")) return "status-provisioning";
    if (s.includes("fail")) return "status-failed";
    return "status-unknown";
  };

  return (
    <div className="app-shell">
      <div className="container">
        <header className="header">
          <h1>Store Provisioning Dashboard</h1>
        </header>

        <section className="create-section card">
          <h2>Create Store</h2>
          <div className="create-form">
            <input
              className="input"
              placeholder="Store Name (e.g. demo)"
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
            />
            <input
              className="input"
              placeholder="Domain (e.g. store1.localhost)"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
            <button className="btn primary" onClick={createStore} disabled={creating}>
              {creating ? "Creating..." : "Create"}
            </button>
          </div>
        </section>

        <section className="list-section">
          <h2>Existing Stores</h2>

          {loading ? (
            <div className="loader">Loading stores…</div>
          ) : stores.length === 0 ? (
            <div className="empty">No stores provisioned yet.</div>
          ) : (
            <div className="stores-grid">
              {stores.map((store) => (
                <article className="store-card" key={store.id}>
                  <div className="store-header">
                    <div className="store-title">
                      <strong className="store-name">{store.store_name}</strong>
                      <span className={`status-badge ${statusClass(store.status)}`}>
                        {store.status || "unknown"}
                      </span>
                    </div>
                    <div className="store-meta">
                      <div className="meta-line">
                        <span className="meta-key">Namespace</span>
                        <span className="meta-val">{store.namespace}</span>
                      </div>
                      <div className="meta-line">
                        <span className="meta-key">Domain</span>
                        <a className="meta-link" href={domainUrl(store.domain)} target="_blank" rel="noreferrer">
                          {store.domain}
                        </a>
                      </div>
                      <div className="meta-line">
    <span className="meta-key">Created</span>
    <span className="meta-val">
      {store.created_at
        ? new Date(store.created_at).toLocaleString()
        : "—"}
    </span>
  </div>

                    </div>
                  </div>

                  <div className="store-actions">
                    <a className="btn link" href={domainUrl(store.domain)} target="_blank" rel="noreferrer">
                      Visit
                    </a>

                    <button
                      className="btn danger"
                      onClick={() => deleteStore(store.id, store.domain)}
                      title="Delete this store and all its Kubernetes resources"
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default App;
