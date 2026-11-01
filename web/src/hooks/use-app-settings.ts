import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SettingsInfo, TemplateInfo } from "../api/types";

/**
 * The server's settings and the agent templates, read as the app starts.
 *
 * Settings describe a server that may have restarted since the page loaded, so opening
 * them asks again, along with whether a newer bundle is out. A failed ask keeps what was
 * shown rather than blanking it.
 */
export function useAppSettings(settingsOpen: boolean, checkVersion: () => void) {
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);

  useEffect(() => {
    api.settings().then(setSettings, () => setSettings(null));
    api.templates().then(setTemplates, () => setTemplates([]));
  }, []);

  useEffect(() => {
    if (!settingsOpen) return;
    api.settings().then(setSettings, () => {});
    checkVersion();
  }, [settingsOpen, checkVersion]);

  return { settings, templates };
}
