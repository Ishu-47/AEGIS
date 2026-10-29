import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ShieldCheck, Eye, EyeOff } from "lucide-react";
import { useApp } from "../App";
import { loginDashboardUser, registerDashboardUser } from "../api/aegis";

export default function AuthPage({ mode }) {
  const isRegister = mode === "register";
  const { refreshSession, registrationAvailable } = useApp();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isRegister) {
        await registerDashboardUser({ email, password });
      } else {
        await loginDashboardUser({ email, password });
      }
      await refreshSession();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || "Could not authenticate. Check the backend and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-ivory px-5 py-10 text-ink">
      <div className="w-full max-w-md animate-fade-in">
        <div className="mb-8 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-oxblood text-ivory">
            <ShieldCheck size={25} />
          </div>
          <div>
            <p className="text-xl font-bold tracking-tight">AEGIS</p>
            <p className="text-[10px] uppercase tracking-[0.22em] text-ink/45">Incident Intelligence</p>
          </div>
        </div>

        <section className="rounded-2xl border border-ink/10 bg-white/60 p-7 shadow-sm sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-oxblood">
            {isRegister ? "Create workspace account" : "Secure workspace"}
          </p>
          <h1 className="mt-2 text-2xl font-semibold">
            {isRegister ? "Create your account" : "Welcome back"}
          </h1>
          <p className="mt-2 text-sm leading-6 text-ink/55">
            {isRegister
              ? "Create an account to manage your own applications. Application ingestion keys remain separate."
              : "Sign in to manage applications, review incidents, and investigate errors."}
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="auth-email" className="block text-sm font-medium">Email</label>
              <input
                id="auth-email"
                type="email"
                autoComplete="email"
                required
                maxLength={320}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-lg border border-ink/15 bg-ivory px-3.5 py-3 text-sm outline-none transition focus:border-oxblood"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label htmlFor="auth-password" className="block text-sm font-medium">Password</label>
              <div className="relative mt-2">
                <input
                  id="auth-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  required
                  minLength={isRegister ? 10 : 1}
                  maxLength={128}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-lg border border-ink/15 bg-ivory px-3.5 py-3 pr-11 text-sm outline-none transition focus:border-oxblood"
                  placeholder={isRegister ? "At least 10 characters" : "Your password"}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink/40 hover:text-ink"
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            {error && (
              <div role="alert" className="rounded-lg border border-danger/20 bg-danger/5 px-3 py-2.5 text-sm text-danger">
                {error}
              </div>
            )}

            <button
              disabled={loading || (isRegister && !registrationAvailable)}
              className="w-full rounded-lg bg-oxblood px-4 py-3 text-sm font-semibold text-ivory transition hover:bg-oxblood-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Please wait..." : isRegister ? "Create account" : "Sign in"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-ink/55">
            {isRegister ? (
              <>Already have an account? <Link to="/login" className="font-semibold text-oxblood hover:underline">Sign in</Link></>
            ) : registrationAvailable ? (
              <>New to AEGIS? <Link to="/register" className="font-semibold text-oxblood hover:underline">Create an account</Link></>
            ) : (
              "Your applications are private to your account."
            )}
          </p>
        </section>
        <p className="mt-5 text-center text-xs text-ink/40">
          Dashboard account ≠ application API key
        </p>
      </div>
    </main>
  );
}
