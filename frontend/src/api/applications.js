
import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 15000,
});

export async function registerApplication(payload) {
  const response = await api.post("/applications", payload);
  return response.data;
}

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
