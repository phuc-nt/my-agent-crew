import { request } from "./http";

/** What a browser's `PushSubscription.toJSON()` gives, as the server keeps it. */
export interface PushSubscriptionBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const pushApi = {
  /** The server's public key, which a subscription is made against. */
  pushKey: () => request<{ key: string }>("/push/key"),
  pushSubscribe: (body: PushSubscriptionBody) =>
    request<{ subscribed: boolean }>("/push/subscriptions", json("POST", body)),
  pushUnsubscribe: (endpoint: string) =>
    request<{ removed: boolean }>("/push/subscriptions", json("DELETE", { endpoint })),
  /** A push to this device alone; `status` is what its push service answered, 0 unreachable. */
  pushTest: (endpoint: string) => request<{ status: number }>("/push/test", json("POST", { endpoint })),
};
