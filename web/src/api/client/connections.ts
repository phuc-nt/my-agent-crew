import type { ConnectionsInfo, CredentialCheck, CredentialsInfo, McpServerInfo, RouteInfo } from "../types";
import { request } from "./http";

type McpServers = { servers: McpServerInfo[] };

export const connectionsApi = {
  connections: () => request<ConnectionsInfo>("/connections"),
  setRoutes: (routes: RouteInfo[]) =>
    request<ConnectionsInfo & { restart_required: string | null }>("/connections/routes", {
      method: "PUT",
      body: JSON.stringify({ routes }),
    }),
  credentials: () => request<CredentialsInfo>("/credentials"),
  setCredential: (name: string, value: string) =>
    request<CredentialsInfo>(`/credentials/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    }),
  removeCredential: (name: string) =>
    request<CredentialsInfo>(`/credentials/${encodeURIComponent(name)}`, { method: "DELETE" }),
  checkCredential: (name: string) =>
    request<CredentialCheck>(`/credentials/${encodeURIComponent(name)}/check`, { method: "POST" }),
  mcpServers: () => request<McpServers>("/mcp"),
  mcpReconnect: (name: string) =>
    request<McpServers>(`/mcp/${encodeURIComponent(name)}/reconnect`, { method: "POST" }),
  /** Where to send the person to sign in; the server answers this only to a loopback address. */
  mcpSignIn: (name: string) =>
    request<{ authorize_url: string }>(`/mcp/${encodeURIComponent(name)}/login`, { method: "POST" }),
  mcpSignOut: (name: string) =>
    request<McpServers>(`/mcp/${encodeURIComponent(name)}/login`, { method: "DELETE" }),
};
