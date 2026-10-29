import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api",
  timeout: 30000,
  withCredentials: true,
});

// Cookie-based sessions are protected with a double-submit CSRF token.
api.interceptors.request.use((config) => {
  const csrf = document.cookie
    .split("; ")
    .find((part) => part.startsWith("aegis_csrf="))
    ?.split("=")
    .slice(1)
    .join("=");

  if (csrf && !["get", "head", "options"].includes((config.method || "get").toLowerCase())) {
    config.headers["X-CSRF-Token"] = decodeURIComponent(csrf);
  }
  return config;
});

// ---------------------------------------------------------------------------
// Dashboard authentication
// ---------------------------------------------------------------------------

export async function getAuthStatus() {
  return (await api.get("/auth/status")).data;
}

export async function registerDashboardUser(payload) {
  return (await api.post("/auth/register", payload)).data;
}

export async function loginDashboardUser(payload) {
  return (await api.post("/auth/login", payload)).data;
}

export async function logoutDashboardUser() {
  return (await api.post("/auth/logout")).data;
}

// ---------------------------------------------------------------------------
// Application management
// ---------------------------------------------------------------------------

export async function registerApplication(payload) {
  return (await api.post("/applications", payload)).data;
}

export async function listApplications() {
  return (await api.get("/applications")).data;
}

export async function deleteApplication(applicationId) {
  return (await api.delete(`/applications/${applicationId}`)).data;
}

export async function rotateApplicationKey(applicationId) {
  return (await api.post(`/applications/${applicationId}/rotate-key`)).data;
}

// ---------------------------------------------------------------------------
// Log submission (dashboard session; API keys are only for external ingestion)
// ---------------------------------------------------------------------------

export async function submitLogs({ applicationId, content, file }) {
  const form = new FormData();
  if (file) form.append("file", file);
  else form.append("content", content);

  return (await api.post(`/dashboard/applications/${applicationId}/logs`, form)).data;
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------

export async function fetchIncidents(applicationId) {
  return (await api.get(`/dashboard/applications/${applicationId}/incidents`)).data;
}

export async function fetchIncident(incidentId) {
  return (await api.get(`/dashboard/incidents/${incidentId}`)).data;
}

export async function triggerInvestigation(incidentId) {
  return (await api.post(`/dashboard/incidents/${incidentId}/investigate`, {})).data;
}

export async function updateIncidentStatus(incidentId, status) {
  return (await api.patch(`/dashboard/incidents/${incidentId}/status`, null, {
    params: { status },
  })).data;
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export async function fetchStats(applicationId) {
  return (await api.get(`/dashboard/applications/${applicationId}/stats`)).data;
}

export default api;
