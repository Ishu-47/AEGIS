import { useState } from "react";
import { useApp } from "../App";
import { deleteApplication, rotateApplicationKey } from "../api/aegis";
import { Copy, Check, RefreshCw, Trash2, ShieldCheck, KeyRound, Layers, X } from "lucide-react";

function copyText(value, onDone) {
  if (!navigator.clipboard?.writeText) {
    window.prompt("Copy this value:", value);
    return;
  }
  navigator.clipboard.writeText(value).then(onDone).catch(() => {
    window.prompt("Copy this value:", value);
  });
}

function SecretModal({ credential, onClose }) {
  const [copied, setCopied] = useState(false);
  if (!credential) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/40 px-4 backdrop-blur-sm" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <div className="w-full max-w-lg rounded-2xl border border-ink/10 bg-ivory p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">Credential updated</p>
            <h2 className="mt-2 text-lg font-semibold">Copy your new API key</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-ink/45 hover:bg-ink/5"><X size={18} /></button>
        </div>
        <p className="mt-3 text-sm leading-6 text-ink/60">
          The previous key has been invalidated. This key is shown only once and is not saved in browser storage.
        </p>
        <div className="mt-4 rounded-xl border border-oxblood/20 bg-oxblood/5 p-4">
          <code className="block break-all text-xs leading-6">{credential.api_key}</code>
          <button
            onClick={() => copyText(credential.api_key, () => setCopied(true))}
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-oxblood px-3 py-2 text-sm font-semibold text-ivory"
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
            {copied ? "Copied" : "Copy API key"}
          </button>
        </div>
        <button onClick={onClose} className="mt-5 w-full rounded-lg border border-ink/15 px-4 py-2.5 text-sm font-medium hover:bg-ink/5">Done</button>
      </div>
    </div>
  );
}

export default function ApplicationsPage() {
  const { applications, refreshApplications } = useApp();
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copiedId, setCopiedId] = useState("");
  const [credential, setCredential] = useState(null);

  async function handleRotate(app) {
    const confirmed = window.confirm(`Rotate the ingestion key for "${app.name}"? The old key will stop working immediately.`);
    if (!confirmed) return;
    setBusyId(app.id);
    setError("");
    setNotice("");
    try {
      const result = await rotateApplicationKey(app.id);
      setCredential({ name: app.name, api_key: result.api_key });
      setNotice(`Key rotated for ${app.name}. Update the integration using the new key.`);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not rotate the API key.");
    } finally {
      setBusyId("");
    }
  }

  async function handleDelete(app) {
    const confirmed = window.confirm(
      `Delete "${app.name}" and all its stored logs, incidents, and investigation reports? This cannot be undone.`,
    );
    if (!confirmed) return;
    setBusyId(app.id);
    setError("");
    setNotice("");
    try {
      await deleteApplication(app.id);
      await refreshApplications();
      setNotice(`${app.name} was deleted.`);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not delete the application.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">Workspace</p>
          <h1 className="mt-2 text-2xl font-semibold">Applications</h1>
          <p className="mt-1 text-sm text-ink/55">Manage connected services and their ingestion credentials.</p>
        </div>
        <div className="rounded-xl border border-ink/10 bg-white/40 px-4 py-3">
          <p className="text-xs text-ink/50">Registered applications</p>
          <p className="mt-1 text-xl font-semibold">{applications.length}</p>
        </div>
      </div>

      {error && <div role="alert" className="rounded-xl border border-danger/20 bg-danger/5 p-4 text-sm text-danger">{error}</div>}
      {notice && <div role="status" className="rounded-xl border border-success/20 bg-success/5 p-4 text-sm text-success">{notice}</div>}

      {applications.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-ink/15 bg-white/25 px-6 py-16 text-center">
          <Layers size={30} className="mx-auto text-ink/30" />
          <h2 className="mt-4 font-semibold">No applications yet</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-ink/55">Use the “+ New” button in the header to register your first application. Its API key will be shown once.</p>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {applications.map((app) => (
            <article key={app.id} className="rounded-2xl border border-ink/10 bg-white/40 p-5">
              <div className="flex items-start gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-oxblood/10 text-oxblood"><Layers size={20} /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-semibold">{app.name}</h2>
                    <span className="rounded-full border border-success/20 bg-success/5 px-2 py-0.5 text-[10px] font-semibold text-success"><ShieldCheck size={11} className="mr-1 inline" />Active</span>
                  </div>
                  <p className="mt-1 text-xs text-ink/50">{app.platform || "Other"} · Created {app.created_at ? new Date(app.created_at).toLocaleDateString() : "date unavailable"}</p>
                  <p className="mt-2 text-sm text-ink/65">{app.description || "No description provided."}</p>
                </div>
              </div>

              <div className="mt-5 rounded-xl border border-ink/8 bg-ivory/70 p-3">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-ink/45">Application ID</p>
                <div className="mt-1 flex items-center gap-2">
                  <code className="min-w-0 flex-1 break-all text-[11px] text-ink/75">{app.id}</code>
                  <button
                    title="Copy application ID"
                    aria-label={`Copy ${app.name} application ID`}
                    onClick={() => copyText(app.id, () => { setCopiedId(app.id); setTimeout(() => setCopiedId(""), 1600); })}
                    className="rounded-lg p-2 text-ink/50 hover:bg-ink/5 hover:text-oxblood"
                  >{copiedId === app.id ? <Check size={15} /> : <Copy size={15} />}</button>
                </div>
              </div>

              <div className="mt-3 flex items-start gap-2 rounded-lg bg-surface/45 p-3">
                <KeyRound size={15} className="mt-0.5 shrink-0 text-ink/50" />
                <p className="text-xs leading-5 text-ink/60">API key is stored as a hash and cannot be retrieved. Rotate it to issue a new key; copy it immediately.</p>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  disabled={busyId === app.id}
                  onClick={() => handleRotate(app)}
                  className="inline-flex items-center gap-2 rounded-lg border border-ink/15 px-3 py-2 text-xs font-semibold transition hover:bg-ink/5 disabled:opacity-50"
                ><RefreshCw size={13} className={busyId === app.id ? "animate-spin" : ""} /> Rotate key</button>
                <button
                  disabled={busyId === app.id}
                  onClick={() => handleDelete(app)}
                  className="inline-flex items-center gap-2 rounded-lg border border-danger/20 px-3 py-2 text-xs font-semibold text-danger transition hover:bg-danger/5 disabled:opacity-50"
                ><Trash2 size={13} /> Delete application</button>
              </div>
            </article>
          ))}
        </div>
      )}
      <SecretModal credential={credential} onClose={() => setCredential(null)} />
    </div>
  );
}
