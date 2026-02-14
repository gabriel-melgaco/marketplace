import axios from "axios";
import { API_BASE_URL } from "@/utils/constants";
import { tokenStorage } from "@/utils/tokenStorage";

const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
