/**
 * Notifications pushed by the server to this device: whether the browser can take them,
 * turning them on and off, and following a tapped notification into the app.
 *
 * The service worker (`public/sw.js`) only shows what arrives. A subscription is made
 * against the server's key; one made against another key (a home restored from elsewhere)
 * can never be pushed to, so it is dropped and the person turns notifications on again.
 */
import { api } from "../api/client";
import type { PushSubscriptionBody } from "../api/client/push";

export type PushState = "unsupported" | "install" | "denied" | "off" | "on";

const SW_URL = "/sw.js";

/** The person said no, or closed the prompt. */
export class PushRefused extends Error {}

function isIos(): boolean {
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function standalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

/** "install" on an iPhone that opened the app in Safari: it pushes only to a Home Screen app. */
export function pushSupport(): "ok" | "install" | "unsupported" {
  if ("serviceWorker" in navigator && "PushManager" in window && "Notification" in window) return "ok";
  return isIos() && !standalone() ? "install" : "unsupported";
}

export function keyBytes(key: string): Uint8Array<ArrayBuffer> {
  const base64 = key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (key.length % 4)) % 4);
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}

function madeWith(sub: PushSubscription, key: string): boolean {
  const used = sub.options.applicationServerKey;
  if (!used) return false;
  const a = new Uint8Array(used);
  const b = keyBytes(key);
  return a.length === b.length && a.every((byte, i) => byte === b[i]);
}

async function current(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration("/");
  return registration ? registration.pushManager.getSubscription() : null;
}

export async function pushState(): Promise<PushState> {
  const support = pushSupport();
  if (support !== "ok") return support;
  if (Notification.permission === "denied") return "denied";
  return (await current()) ? "on" : "off";
}

/** Asks first, as the press's own act: Safari allows the prompt only from a tap. */
export async function enablePush(): Promise<void> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new PushRefused(permission);
  const registration = await navigator.serviceWorker.register(SW_URL);
  await navigator.serviceWorker.ready;
  const { key } = await api.pushKey();
  let sub = await registration.pushManager.getSubscription();
  if (sub && !madeWith(sub, key)) {
    await sub.unsubscribe();
    sub = null;
  }
  sub ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
  await api.pushSubscribe(sub.toJSON() as PushSubscriptionBody);
}

export async function disablePush(): Promise<void> {
  const sub = await current();
  if (!sub) return;
  await api.pushUnsubscribe(sub.endpoint).catch(() => undefined);
  await sub.unsubscribe();
}

/** What the push service answered for a test push to this device. */
export async function testPush(): Promise<number> {
  const sub = await current();
  if (!sub) return 0;
  return (await api.pushTest(sub.endpoint)).status;
}

/**
 * As the app starts: a tapped notification moves an open page to where it points, and a
 * subscription this device holds is handed to the server again, which may have lost it.
 */
export function startPush(): void {
  if (pushSupport() !== "ok") return;
  navigator.serviceWorker.addEventListener("message", (event: MessageEvent) => {
    const data = event.data as { type?: string; url?: string } | null;
    if (data?.type === "crew-open" && data.url) window.location.hash = new URL(data.url).hash;
  });
  void (async () => {
    const sub = await current();
    if (!sub) return;
    const { key } = await api.pushKey();
    if (madeWith(sub, key)) await api.pushSubscribe(sub.toJSON() as PushSubscriptionBody);
    else await sub.unsubscribe();
  })().catch(() => undefined);
}
