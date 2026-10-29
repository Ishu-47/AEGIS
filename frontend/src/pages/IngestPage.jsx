import { useState } from "react";
import { useApp } from "../App";
import { submitLogs } from "../api/aegis";
import { Upload, FileText, AlertCircle, CheckCircle2 } from "lucide-react";

export default function IngestPage() {
  const { selected, allApplicationsSelected } = useApp();
  const [mode, setMode] = useState("paste");
  const [content, setContent] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setResult(null);

    if (!selected) {
      setError("Select an application first.");
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
      const data = await submitLogs({
        applicationId: selected.id,
        content: mode === "paste" ? content : "",
        file: mode === "upload" ? file : null,
      });
      setResult(data);
      setContent("");
      setFile(null);
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not process these logs.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">
          Diagnostic Intake
        </p>
        <h2 className="mt-2 text-xl font-semibold">Bring your logs</h2>
        <p className="mt-1 text-sm text-ink/55">
          Structured JSON, plain text, or files from any application.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        {/* Input form */}
        <div className="rounded-2xl border border-ink/8 bg-white/40 p-6">
          {/* Mode tabs */}
          <div className="flex gap-2 border-b border-ink/8 pb-4">
            {["paste", "upload"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
                  mode === m
                    ? "bg-oxblood text-ivory"
                    : "bg-surface/60 text-ink/60 hover:text-ink"
                }`}
              >
                {m === "paste" ? (
                  <>
                    <FileText size={14} /> Paste logs
                  </>
                ) : (
                  <>
                    <Upload size={14} /> Upload file
                  </>
                )}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="mt-5 space-y-5">
            {/* Source application */}
            <div>
              <p className="text-sm font-medium">Source application</p>
              <p className="mt-1 text-sm text-ink/55">
                {selected?.name || (allApplicationsSelected
                  ? "Choose a specific application in the header to ingest logs."
                  : "Select an application in the header.")}
              </p>
            </div>

            {mode === "paste" ? (
              <div>
                <label
                  htmlFor="log-content"
                  className="block text-sm font-medium"
                >
                  Console output, stack trace, or error messages
                </label>
                <textarea
                  id="log-content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={14}
                  maxLength={500000}
                  placeholder={`2026-10-25T10:21:30Z ERROR PaymentService - Payment timeout\njava.net.SocketTimeoutException: Read timed out\n    at java.net.Socket.read(Socket.java:717)\n\n{"timestamp":"2026-10-25T10:21:31Z","level":"ERROR","service":"OrderService","message":"Failed to process order #1234","correlation_id":"abc-123"}`}
                  className="mt-2 w-full rounded-xl border border-ink/12 bg-ivory px-4 py-3 font-mono text-xs leading-6 outline-none transition focus:border-oxblood"
                />
                <p className="mt-2 text-xs text-ink/40">
                  Supports plain text logs, JSON objects, JSON arrays, and
                  JSON-Lines format. Up to 500,000 characters.
                </p>
              </div>
            ) : (
              <div className="rounded-xl border-2 border-dashed border-ink/15 p-8 text-center transition hover:border-ink/25">
                <Upload
                  size={28}
                  className="mx-auto text-ink/30"
                />
                <label
                  htmlFor="log-file"
                  className="mt-3 block text-sm font-medium cursor-pointer"
                >
                  Choose a diagnostic file
                </label>
                <p className="mt-1 text-xs text-ink/50">
                  .log, .txt, or .json · Maximum 1 MB
                </p>
                <input
                  id="log-file"
                  type="file"
                  accept=".log,.txt,.json,text/plain,application/json"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="mt-4 block w-full text-sm file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-surface file:px-4 file:py-2 file:text-sm file:font-medium file:text-ink"
                />
                {file && (
                  <p className="mt-3 text-xs text-ink/60">
                    {file.name} · {(file.size / 1024).toFixed(1)} KB
                  </p>
                )}
              </div>
            )}

            <button
              disabled={loading || !selected}
              className="w-full rounded-xl bg-oxblood px-4 py-3 text-sm font-semibold text-ivory transition hover:bg-oxblood-dark disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-ivory/30 border-t-ivory" />
                  Processing logs...
                </span>
              ) : (
                "Ingest diagnostic data"
              )}
            </button>
          </form>
        </div>

        {/* Results panel */}
        <div className="space-y-4">
          {error && (
            <div className="flex items-start gap-3 rounded-xl border border-danger/20 bg-danger/5 p-4 animate-fade-in">
              <AlertCircle
                size={16}
                className="mt-0.5 shrink-0 text-danger"
              />
              <p className="text-sm text-danger">{error}</p>
            </div>
          )}

          {result && (
            <div className="rounded-xl border border-success/20 bg-success/5 p-5 animate-fade-in">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-success" />
                <p className="text-sm font-semibold text-success">
                  Ingestion complete
                </p>
              </div>
              <div className="mt-3 space-y-1">
                <p className="text-sm text-ink/70">
                  <span className="font-semibold">{result.accepted}</span>{" "}
                  events accepted
                </p>
                {result.incidents_updated > 0 && (
                  <p className="text-sm text-ink/70">
                    <span className="font-semibold">
                      {result.incidents_updated}
                    </span>{" "}
                    incidents touched
                  </p>
                )}
              </div>
            </div>
          )}

          {result?.events && result.events.length > 0 && (
            <div className="rounded-xl border border-ink/8 bg-white/30 p-5 animate-fade-in">
              <h3 className="text-sm font-semibold">
                Parsed events
                <span className="ml-2 rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-ink/60">
                  {result.events.length}
                </span>
              </h3>
              <div className="mt-3 max-h-96 space-y-2 overflow-y-auto">
                {result.events.slice(0, 20).map((ev) => (
                  <div
                    key={ev.id}
                    className="rounded-lg border border-ink/6 p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase severity-${ev.severity?.toLowerCase()}`}
                      >
                        {ev.severity}
                      </span>
                      <span className="text-xs text-ink/50">{ev.service}</span>
                      <span className="ml-auto text-[10px] text-ink/40">
                        {new Date(ev.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-1.5 break-words font-mono text-[11px] leading-5 text-ink/80">
                      {ev.message?.slice(0, 300)}
                      {ev.message?.length > 300 && "..."}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
