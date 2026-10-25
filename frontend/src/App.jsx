
import { useEffect, useState } from "react";
import { getHealth } from "./api/health";

export default function App() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function checkHealth() {
    setLoading(true);
    setError("");

    try {
      const data = await getHealth();
      setHealth(data);
    } catch {
      setHealth(null);
      setError("Unable to connect to the AEGIS backend.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 p-8 text-slate-100">
      <div className="mx-auto max-w-3xl">
        <p className="text-sm font-semibold tracking-widest text-cyan-400">
          AEGIS / SYSTEM MONITOR
        </p>

        <h1 className="mt-3 text-4xl font-bold">
          Incident Intelligence
        </h1>

        <p className="mt-2 text-slate-400">
          Monitor services and investigate application failures.
        </p>

        <section className="mt-10 rounded-xl border border-slate-800 bg-slate-900 p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">AEGIS API</h2>
              <p className="mt-1 text-sm text-slate-400">
                Backend connectivity
              </p>
            </div>

            <span
              className={`rounded-full px-3 py-1 text-sm ${
                health
                  ? "bg-emerald-950 text-emerald-400"
                  : error
                    ? "bg-red-950 text-red-400"
                    : "bg-slate-800 text-slate-300"
              }`}
            >
              {loading
                ? "Checking..."
                : health
                  ? health.status
                  : "Unavailable"}
            </span>
          </div>

          {error && (
            <p className="mt-4 text-sm text-red-400">{error}</p>
          )}

          {health && (
            <p className="mt-4 break-all text-sm text-slate-400">
              Last checked: {health.timestamp}
            </p>
          )}

          <button
            onClick={checkHealth}
            disabled={loading}
            className="mt-6 rounded-lg bg-cyan-500 px-4 py-2
                       font-medium text-slate-950 hover:bg-cyan-400
                       disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Checking..." : "Check again"}
          </button>
        </section>
      </div>
    </main>
  );
}
