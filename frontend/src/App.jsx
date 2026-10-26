
import { useEffect, useState } from "react";
import {
  fetchLogs,
  registerApplication,
  submitLogs,
} from "./api/applications";

const STORAGE_KEY = "aegis.applications";

function readApplications() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export default function App() {
  const [applications, setApplications] = useState(readApplications);
  const [selectedId, setSelectedId] = useState(
    () => readApplications()[0]?.id || "",
  );
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState("paste");
  const [content, setContent] = useState("");
  const [file, setFile] = useState(null);
  const [logs, setLogs] = useState([]);
  const [newKey, setNewKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = applications.find((item) => item.id === selectedId);

  
useEffect(() => {
  if (!selected) {
    setLogs([]);
    return;
  }

  fetchLogs(selected.id, selected.api_key)
    .then((data) => {
      // Support either an array or an object containing events.
      const events = Array.isArray(data)
        ? data
        : Array.isArray(data?.events)
          ? data.events
          : [];

      setLogs(events);
    })
    .catch(() => setLogs([]));
}, [selectedId]);


  function saveApplications(next) {
    setApplications(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  async function handleRegister(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setNewKey("");
    setLoading(true);

    try {
      const created = await registerApplication({ name, description });
      const next = [...applications, created];
      saveApplications(next);
      setSelectedId(created.id);
      setName("");
      setDescription("");
      setLogs([]);
      setNewKey(created.api_key);
      setNotice("Application registered successfully.");
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not register the application.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitLogs(event) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!selected) {
      setError("Register or select an application first.");
      return;
    }

    if (mode === "paste" && !content.trim()) {
      setError("Paste some log output before submitting.");
      return;
    }

    if (mode === "upload" && !file) {
      setError("Choose a .log, .txt, or .json file.");
      return;
    }

    if (file && file.size > 1_000_000) {
      setError("Maximum file size is 1 MB.");
      return;
    }

    setLoading(true);
    try {
      const result = await submitLogs({
        applicationId: selected.id,
        apiKey: selected.api_key,
        content: mode === "paste" ? content : "",
        file: mode === "upload" ? file : null,
      });

      setLogs((previous) => [...result.events, ...previous]);
      setContent("");
      setFile(null);
      setNotice(`${result.accepted} diagnostic events ingested.`);
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not process these logs.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-ivory text-ink">
      <header className="border-b border-ink/10 px-6 py-5 md:px-10">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-oxblood">
              AEGIS / Incident Intelligence
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
              Understand what went wrong.
            </h1>
          </div>
          <span className="hidden rounded-full border border-ink/15 px-3 py-1.5 text-xs md:inline-block">
            EARLY ACCESS · MVP
          </span>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-8 px-6 py-8 md:px-10 lg:grid-cols-[0.85fr_1.15fr]">
        <section className="space-y-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">
              01 — Applications
            </p>
            <h2 className="mt-2 text-xl font-semibold">
              Your applications
            </h2>
            <p className="mt-1 text-sm text-ink/65">
              Register an application before sending its diagnostic data.
            </p>
          </div>

          <div className="rounded-2xl border border-ink/10 bg-white/45 p-5">
            <label className="text-sm font-medium" htmlFor="application">
              Selected application
            </label>
            <select
              id="application"
              value={selectedId}
              onChange={(event) => setSelectedId(event.target.value)}
              className="mt-2 w-full rounded-lg border border-ink/15 bg-ivory px-3 py-3 text-sm outline-none focus:border-oxblood"
            >
              <option value="">Choose an application</option>
              {applications.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>

            {selected && (
              <p className="mt-3 break-all text-xs text-ink/55">
                ID: {selected.id}
              </p>
            )}
          </div>

          <form
            onSubmit={handleRegister}
            className="rounded-2xl border border-ink/10 bg-surface/60 p-5"
          >
            <h3 className="font-semibold">Register application</h3>
            <label htmlFor="name" className="mt-4 block text-sm font-medium">
              Application name
            </label>
            <input
              id="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              minLength={2}
              maxLength={100}
              required
              placeholder="e.g. Inventory API"
              className="mt-2 w-full rounded-lg border border-ink/15 bg-ivory px-3 py-3 text-sm outline-none focus:border-oxblood"
            />

            <label
              htmlFor="description"
              className="mt-4 block text-sm font-medium"
            >
              Description <span className="text-ink/45">(optional)</span>
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={500}
              rows={2}
              placeholder="What does this application do?"
              className="mt-2 w-full rounded-lg border border-ink/15 bg-ivory px-3 py-3 text-sm outline-none focus:border-oxblood"
            />

            <button
              disabled={loading}
              className="mt-4 w-full rounded-lg bg-oxblood px-4 py-3 text-sm font-semibold text-ivory transition hover:bg-oxblood/90 disabled:opacity-50"
            >
              {loading ? "Working..." : "Register application"}
            </button>

            {newKey && (
              <div className="mt-4 rounded-lg border border-oxblood/25 bg-ivory p-3">
                <p className="text-sm font-semibold">Ingestion API key</p>
                <p className="mt-1 break-all font-mono text-xs">{newKey}</p>
                <p className="mt-2 text-xs text-ink/60">
                  Copy this key and keep it private. It is shown here only
                  once by the backend.
                </p>
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(newKey)}
                  className="mt-3 text-sm font-semibold text-oxblood underline"
                >
                  Copy key
                </button>
              </div>
            )}
          </form>
        </section>

        <section className="space-y-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">
              02 — Diagnostic intake
            </p>
            <h2 className="mt-2 text-xl font-semibold">Bring your logs</h2>
            <p className="mt-1 text-sm text-ink/65">
              Structured JSON or ordinary text from any application.
            </p>
          </div>

          <div className="rounded-2xl border border-ink/10 bg-white/45 p-5 md:p-6">
            <div className="flex gap-2 border-b border-ink/10 pb-4">
              {["paste", "upload"].map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setMode(item)}
                  className={`rounded-lg px-4 py-2 text-sm font-medium capitalize ${
                    mode === item
                      ? "bg-oxblood text-ivory"
                      : "bg-surface text-ink/70 hover:text-ink"
                  }`}
                >
                  {item === "paste" ? "Paste logs" : "Upload file"}
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmitLogs}>
              <label className="mt-5 block text-sm font-medium">
                Source application
              </label>
              <p className="mt-1 text-sm text-ink/60">
                {selected?.name || "Select an application on the left."}
              </p>

              {mode === "paste" ? (
                <>
                  <label
                    htmlFor="logs"
                    className="mt-5 block text-sm font-medium"
                  >
                    Console output or stack trace
                  </label>
                  <textarea
                    id="logs"
                    value={content}
                    onChange={(event) => setContent(event.target.value)}
                    rows={11}
                    maxLength={500000}
                    placeholder={`2026-10-25T10:21:30Z ERROR PaymentService - Payment timeout\njava.net.SocketTimeoutException: Read timed out`}
                    className="mt-2 w-full rounded-lg border border-ink/15 bg-ivory px-3 py-3 font-mono text-xs leading-6 outline-none focus:border-oxblood"
                  />
                  <p className="mt-2 text-xs text-ink/50">
                    Up to 500,000 characters per submission.
                  </p>
                </>
              ) : (
                <div className="mt-5 rounded-xl border border-dashed border-ink/25 p-6">
                  <label
                    htmlFor="file"
                    className="block text-sm font-medium"
                  >
                    Choose a diagnostic file
                  </label>
                  <p className="mt-1 text-xs text-ink/60">
                    .log, .txt, or .json · Maximum 1 MB
                  </p>
                  <input
                    id="file"
                    type="file"
                    accept=".log,.txt,.json,text/plain,application/json"
                    onChange={(event) =>
                      setFile(event.target.files?.[0] || null)
                    }
                    className="mt-4 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-surface file:px-3 file:py-2 file:text-ink"
                  />
                  {file && (
                    <p className="mt-3 break-all text-xs text-ink/70">
                      {file.name} · {(file.size / 1024).toFixed(1)} KB
                    </p>
                  )}
                </div>
              )}

              <button
                disabled={loading || !selected}
                className="mt-5 w-full rounded-lg bg-oxblood px-4 py-3 text-sm font-semibold text-ivory hover:bg-oxblood/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Processing logs..." : "Ingest diagnostic data"}
              </button>
            </form>
          </div>

          {(error || notice) && (
            <div
              role="status"
              className={`rounded-lg border p-4 text-sm ${
                error
                  ? "border-red-800/20 bg-red-50 text-red-800"
                  : "border-oxblood/20 bg-surface/60 text-ink"
              }`}
            >
              {error || notice}
            </div>
          )}

          <div className="rounded-2xl border border-ink/10 bg-white/45 p-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Normalized events</h3>
              <span className="rounded-full bg-surface px-3 py-1 text-xs">
                {logs.length} events
              </span>
            </div>

            {logs.length === 0 ? (
              <p className="py-8 text-center text-sm text-ink/55">
                Your ingested diagnostic events will appear here.
              </p>
            ) : (
              <div className="mt-4 space-y-3">
                {logs.slice(0, 20).map((log) => (
                  <article
                    key={log.id}
                    className="rounded-lg border border-ink/10 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-oxblood/10 px-2 py-1 text-xs font-semibold text-oxblood">
                        {log.severity}
                      </span>
                      <span className="text-xs text-ink/55">
                        {log.service}
                      </span>
                      <span className="ml-auto text-xs text-ink/45">
                        {new Date(log.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-2 break-words font-mono text-xs leading-5">
                      {log.message}
                    </p>
                    {log.correlation_id && (
                      <p className="mt-2 break-all text-xs text-ink/55">
                        Correlation ID: {log.correlation_id}
                      </p>
                    )}
                  </article>
                ))}
                {logs.length > 20 && (
                  <p className="text-center text-xs text-ink/55">
                    Showing the latest 20 events.
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      </div>

      <footer className="border-t border-ink/10 px-6 py-5 text-center text-xs text-ink/50">
        AEGIS · Evidence before assumptions.
      </footer>
    </main>
  );
}
