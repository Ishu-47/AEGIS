import { useState } from "react";
import { useApp } from "../App";
import { registerApplication } from "../api/aegis";
import { X, Copy, Check } from "lucide-react";

export default function RegisterModal({ onClose }) {
  const { addApplication } = useApp();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [platform, setPlatform] = useState("Python");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const result = await registerApplication({ name, description, platform });
      addApplication(result);
      setCreated(result);
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not register the application.",
      );
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(created.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-md rounded-2xl border border-ink/10 bg-ivory p-6 shadow-2xl animate-fade-in">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Register application</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-ink/40 transition hover:bg-ink/5 hover:text-ink"
          >
            <X size={18} />
          </button>
        </div>

        {!created ? (
          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <div>
              <label htmlFor="reg-name" className="block text-sm font-medium">
                Application name
              </label>
              <input
                id="reg-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                minLength={2}
                maxLength={100}
                placeholder="e.g. Inventory API"
                className="mt-2 w-full rounded-lg border border-ink/15 bg-white/50 px-3 py-2.5 text-sm outline-none transition focus:border-oxblood"
              />
            </div>
            <div>
              <label htmlFor="reg-platform" className="block text-sm font-medium">
                Platform
              </label>
              <select
                id="reg-platform"
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="mt-2 w-full rounded-lg border border-ink/15 bg-white/50 px-3 py-2.5 text-sm outline-none transition focus:border-oxblood"
              >
                {["Python", "Java", "Node.js", "JavaScript", "Go", "Ruby", "PHP", ".NET", "Rust", "Other"].map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="reg-desc" className="block text-sm font-medium">
                Description{" "}
                <span className="text-ink/40">(optional)</span>
              </label>
              <textarea
                id="reg-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={500}
                rows={2}
                placeholder="What does this application do?"
                className="mt-2 w-full rounded-lg border border-ink/15 bg-white/50 px-3 py-2.5 text-sm outline-none transition focus:border-oxblood"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}

            <button
              disabled={loading}
              className="w-full rounded-lg bg-oxblood px-4 py-2.5 text-sm font-semibold text-ivory transition hover:bg-oxblood-dark disabled:opacity-50"
            >
              {loading ? "Registering..." : "Register application"}
            </button>
          </form>
        ) : (
          <div className="mt-5 space-y-4 animate-fade-in">
            <div className="rounded-xl border border-success/20 bg-success/5 p-4">
              <p className="text-sm font-semibold text-success">
                ✓ Application registered
              </p>
              <p className="mt-1 text-sm text-ink/60">{created.name}</p>
            </div>

            <div className="rounded-xl border border-oxblood/20 bg-oxblood/5 p-4">
              <p className="text-sm font-semibold">Ingestion API Key</p>
              <p className="mt-2 break-all font-mono text-xs leading-relaxed">
                {created.api_key}
              </p>
              <p className="mt-2 text-xs text-ink/50">
                Copy this key now — it won't be shown again.
              </p>
              <button
                onClick={handleCopy}
                className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-oxblood transition hover:text-oxblood-dark"
              >
                {copied ? (
                  <>
                    <Check size={14} /> Copied
                  </>
                ) : (
                  <>
                    <Copy size={14} /> Copy key
                  </>
                )}
              </button>
            </div>

            <button
              onClick={onClose}
              className="w-full rounded-lg border border-ink/12 px-4 py-2.5 text-sm font-medium transition hover:bg-ink/5"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
