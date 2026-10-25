
import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 5000,
});

export async function getHealth() {
  const response = await api.get("/health");
  return response.data;
}
