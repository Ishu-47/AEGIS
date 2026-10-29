import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 30000,
});

// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

export async function registerApplication(payload) {
  const response = await api.post("/applications", payload);
  return response.data;
}

export async function listApplications() {
  const response = await api.get("/applications");
  return response.data;
}

// ---------------------------------------------------------------------------
// Log submission
// ---------------------------------------------------------------------------

export async function submitLogs({ applicationId, apiKey, content, file }) {
  const form = new FormData();

  if (file) {
    form.append("file", file);
  } else {
    form.append("content", content);
  }

  const response = await api.post(
    `/applications/${applicationId}/logs`,
    form,
    { headers: { "X-API-Key": apiKey } },
  );

  return response.data;
}

export async function fetchLogs(applicationId, apiKey) {
  const response = await api.get(
    `/applications/${applicationId}/logs`,
    { headers: { "X-API-Key": apiKey } },
  );

  return response.data;
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------

export async function fetchIncidents(applicationId, apiKey) {
  const response = await api.get(
    `/applications/${applicationId}/incidents`,
    { headers: { "X-API-Key": apiKey } },
  );
  return response.data;
}

export async function fetchIncident(incidentId, apiKey) {
  const response = await api.get(
    `/incidents/${incidentId}`,
    { headers: { "X-API-Key": apiKey } },
  );
  return response.data;
}

export async function triggerInvestigation(incidentId, apiKey) {
  const response = await api.post(
    `/incidents/${incidentId}/investigate`,
    {},
    { headers: { "X-API-Key": apiKey } },
  );
  return response.data;
}

export async function updateIncidentStatus(incidentId, status, apiKey) {
  const response = await api.patch(
    `/incidents/${incidentId}/status`,
    null,
    {
      params: { status },
      headers: { "X-API-Key": apiKey },
    },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

export async function fetchStats(applicationId, apiKey) {
  const response = await api.get(
    `/applications/${applicationId}/stats`,
    { headers: { "X-API-Key": apiKey } },
  );
  return response.data;
}
