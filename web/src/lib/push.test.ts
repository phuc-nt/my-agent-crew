import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { api } from "../api/client";
import { disablePush, enablePush, keyBytes, PushRefused, pushState, pushSupport, testPush } from "./push";

const KEY = "BAEC"; // three bytes: 4, 1, 2
const OTHER = "BAED";

class FakeSub {
  unsubscribed = false;
  constructor(
    public endpoint: string,
    key: string,
  ) {
    this.options = { applicationServerKey: keyBytes(key).buffer };
  }
  options: { applicationServerKey: ArrayBuffer };
  toJSON() {
    return { endpoint: this.endpoint, keys: { p256dh: "p", auth: "a" } };
  }
  async unsubscribe() {
    this.unsubscribed = true;
    return true;
  }
}

let held: FakeSub | null;
let permission: NotificationPermission;
let answer: NotificationPermission;
const pushManager = {
  getSubscription: async () => held,
  subscribe: vitest.fn(async ({ applicationServerKey }: { applicationServerKey: Uint8Array }) => {
    held = new FakeSub("https://push.example/new", btoa(String.fromCharCode(...applicationServerKey)));
    return held;
  }),
};
const registration = { pushManager };

function pushCapable(registered = true) {
  vitest.stubGlobal("PushManager", class {});
  vitest.stubGlobal("Notification", {
    get permission() {
      return permission;
    },
    requestPermission: async () => (permission = answer),
  });
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      getRegistration: async () => (registered ? registration : undefined),
      register: async () => registration,
      ready: Promise.resolve(registration),
      addEventListener: () => {},
    },
  });
}

beforeEach(() => {
  held = null;
  permission = "default";
  answer = "granted";
  pushManager.subscribe.mockClear();
  vitest.spyOn(api, "pushKey").mockResolvedValue({ key: KEY });
  vitest.spyOn(api, "pushSubscribe").mockResolvedValue({ subscribed: true });
  vitest.spyOn(api, "pushUnsubscribe").mockResolvedValue({ removed: true });
  vitest.spyOn(api, "pushTest").mockResolvedValue({ status: 201 });
});

afterEach(() => {
  vitest.unstubAllGlobals();
  vitest.restoreAllMocks();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("what this browser can do", () => {
  it("is unsupported without a service worker, and asks an iPhone in Safari to install", () => {
    expect(pushSupport()).toBe("unsupported");
    vitest.spyOn(navigator, "userAgent", "get").mockReturnValue("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)");
    expect(pushSupport()).toBe("install");
  });

  it("reads off, on and denied from the permission and the subscription", async () => {
    pushCapable();
    expect(await pushState()).toBe("off");
    held = new FakeSub("https://push.example/1", KEY);
    expect(await pushState()).toBe("on");
    permission = "denied";
    expect(await pushState()).toBe("denied");
  });

  it("decodes the server's key from base64url", () => {
    expect([...keyBytes("-_8")]).toEqual([251, 255]);
  });
});

describe("turning notifications on and off", () => {
  it("asks, subscribes against the server's key and hands the subscription over", async () => {
    pushCapable();
    await enablePush();
    expect([...pushManager.subscribe.mock.calls[0][0].applicationServerKey]).toEqual([4, 1, 2]);
    expect(api.pushSubscribe).toHaveBeenCalledWith(expect.objectContaining({ endpoint: "https://push.example/new" }));
  });

  it("stops at a refusal without subscribing", async () => {
    pushCapable();
    answer = "denied";
    await expect(enablePush()).rejects.toBeInstanceOf(PushRefused);
    expect(pushManager.subscribe).not.toHaveBeenCalled();
  });

  it("drops a subscription made against another key and makes a new one", async () => {
    pushCapable();
    const stale = new FakeSub("https://push.example/old", OTHER);
    held = stale;
    await enablePush();
    expect(stale.unsubscribed).toBe(true);
    expect(pushManager.subscribe).toHaveBeenCalled();
  });

  it("keeps a subscription already made against the server's key", async () => {
    pushCapable();
    held = new FakeSub("https://push.example/kept", KEY);
    await enablePush();
    expect(pushManager.subscribe).not.toHaveBeenCalled();
    expect(api.pushSubscribe).toHaveBeenCalledWith(expect.objectContaining({ endpoint: "https://push.example/kept" }));
  });

  it("tests and turns off this device's subscription", async () => {
    pushCapable();
    const sub = new FakeSub("https://push.example/1", KEY);
    held = sub;
    expect(await testPush()).toBe(201);
    expect(api.pushTest).toHaveBeenCalledWith("https://push.example/1");
    await disablePush();
    expect(api.pushUnsubscribe).toHaveBeenCalledWith("https://push.example/1");
    expect(sub.unsubscribed).toBe(true);
  });
});
