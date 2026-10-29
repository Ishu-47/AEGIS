import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { useState, useEffect, createContext, useContext, useCallback } from "react";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import IngestPage from "./pages/IngestPage";
import IncidentsPage from "./pages/IncidentsPage";
import IncidentDetailPage from "./pages/IncidentDetailPage";
import ApiDocsPage from "./pages/ApiDocsPage";
import ApplicationsPage from "./pages/ApplicationsPage";
import AuthPage from "./pages/AuthPage";
import { getAuthStatus, listApplications, logoutDashboardUser } from "./api/aegis";

const SELECTED_APP_KEY = "aegis.selectedApplicationId";
// Remove the previous version's plaintext application/API-key cache.
if (typeof window !== "undefined") localStorage.removeItem("aegis.applications");

export const AppContext = createContext(null);

export function useApp() {
  return useContext(AppContext);
}

function FullPageLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ivory text-sm text-ink/60">
      <div className="flex items-center gap-3">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-oxblood/20 border-t-oxblood" />
        Loading AEGIS...
      </div>
    </div>
  );
}

function AppRoutes() {
  const [authLoading, setAuthLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [registrationAvailable, setRegistrationAvailable] = useState(false);
  const [email, setEmail] = useState("");
  const [applications, setApplications] = useState([]);
  const [selectedId, setSelectedIdState] = useState(() => localStorage.getItem(SELECTED_APP_KEY) || "");

  const allApplicationsSelected = selectedId === "__all__" && applications.length > 1;
  const selected = applications.find((item) => item.id === selectedId) || null;

  const setSelectedId = useCallback((id) => {
    setSelectedIdState(id || "");
    if (id) localStorage.setItem(SELECTED_APP_KEY, id);
    else localStorage.removeItem(SELECTED_APP_KEY);
  }, []);

  const refreshApplications = useCallback(async () => {
    const next = await listApplications();
    setApplications(next);
    const stored = localStorage.getItem(SELECTED_APP_KEY);
    if ((stored === "__all__" && next.length > 1) || (stored && next.some((item) => item.id === stored))) {
      setSelectedIdState(stored);
    } else if (next.length === 1) {
      setSelectedIdState(next[0].id);
      localStorage.setItem(SELECTED_APP_KEY, next[0].id);
    } else {
      setSelectedIdState("");
      localStorage.removeItem(SELECTED_APP_KEY);
    }
    return next;
  }, []);

  const refreshSession = useCallback(async () => {
    const status = await getAuthStatus();
    setAuthenticated(Boolean(status.authenticated));
    setRegistrationAvailable(Boolean(status.registration_available));
    setEmail(status.email || "");
    if (status.authenticated) {
      await refreshApplications();
    } else {
      setApplications([]);
      setSelectedIdState("");
      localStorage.removeItem(SELECTED_APP_KEY);
    }
    return status;
  }, [refreshApplications]);

  useEffect(() => {
    refreshSession()
      .catch(() => {
        setAuthenticated(false);
        setApplications([]);
      })
      .finally(() => setAuthLoading(false));
  }, [refreshSession]);

  const addApplication = useCallback((created) => {
    const safeApp = {
      id: created.id,
      name: created.name,
      description: created.description || "",
      platform: created.platform || "Other",
      created_at: created.created_at,
    };
    const next = [...applications.filter((item) => item.id !== safeApp.id), safeApp];
    setApplications(next);
    // Keep the current choice; only auto-select if this is the sole app.
    if (next.length === 1 && !selectedId) setSelectedId(safeApp.id);
    // Never persist the one-time API key in browser storage.
  }, [applications, selectedId, setSelectedId]);

  const logout = useCallback(async () => {
    try {
      await logoutDashboardUser();
    } catch {
      // Clear local UI state even if the server is temporarily unreachable.
    } finally {
      setAuthenticated(false);
      setEmail("");
      setApplications([]);
      setSelectedIdState("");
      localStorage.removeItem(SELECTED_APP_KEY);
    }
  }, []);

  const contextValue = {
    authenticated,
    authLoading,
    registrationAvailable,
    email,
    applications,
    selectedId,
    setSelectedId,
    selected,
    allApplicationsSelected,
    addApplication,
    refreshApplications,
    refreshSession,
    logout,
  };

  if (authLoading) return <FullPageLoading />;

  return (
    <AppContext.Provider value={contextValue}>
      <Routes>
        <Route
          path="/login"
          element={
            authenticated
              ? <Navigate to="/" replace />
              : <AuthPage mode="login" />
          }
        />
        <Route
          path="/register"
          element={
            authenticated
              ? <Navigate to="/" replace />
              : registrationAvailable
                ? <AuthPage mode="register" />
                : <Navigate to="/login" replace />
          }
        />
        <Route
          element={authenticated ? <Layout /> : <Navigate to="/login" replace />}
        >
          <Route index element={<DashboardPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="ingest" element={<IngestPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="incidents/:id" element={<IncidentDetailPage />} />
          <Route path="api-docs" element={<ApiDocsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AppContext.Provider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
