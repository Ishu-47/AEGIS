import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect, createContext, useContext } from "react";
import Layout from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import IngestPage from "./pages/IngestPage";
import IncidentsPage from "./pages/IncidentsPage";
import IncidentDetailPage from "./pages/IncidentDetailPage";
import ApiDocsPage from "./pages/ApiDocsPage";

const STORAGE_KEY = "aegis.applications";

function readApplications() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export const AppContext = createContext(null);

export function useApp() {
  return useContext(AppContext);
}

export default function App() {
  const [applications, setApplications] = useState(readApplications);
  const [selectedId, setSelectedId] = useState(
    () => readApplications()[0]?.id || "",
  );

  const selected = applications.find((a) => a.id === selectedId) || null;

  function saveApplications(next) {
    setApplications(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  function addApplication(app) {
    const next = [...applications, app];
    saveApplications(next);
    setSelectedId(app.id);
  }

  const ctx = {
    applications,
    selectedId,
    setSelectedId,
    selected,
    addApplication,
  };

  return (
    <AppContext.Provider value={ctx}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="ingest" element={<IngestPage />} />
            <Route path="incidents" element={<IncidentsPage />} />
            <Route path="incidents/:id" element={<IncidentDetailPage />} />
            <Route path="api-docs" element={<ApiDocsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppContext.Provider>
  );
}
