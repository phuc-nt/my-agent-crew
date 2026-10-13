// Where an agent's browser may still be signed in, on its browser card: the hosts the server
// tells of, how many of them are shown, and what is said where there is none.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { BROWSER_POLL_MS } from "../../hooks/use-agent-browser";
import { OPEN, READ, buttons, clock, crew, pass, saidAloud, sent, settle, show } from "../../test/browser-card-screen";
import { browserTab } from "../../test/fake-browser";

const LABEL = "Có thể đang đăng nhập ở";
const NONE = "Chưa thấy đăng nhập ở máy chủ nào.";
const CAVEAT =
  "Đoán từ cookie còn hạn trong hồ sơ trình duyệt: là dấu hiệu, không phải bằng chứng. Trang có thể đã tự đăng xuất, và có trang giữ cookie như vậy cho cả người chưa đăng nhập.";
const START = "Mở cửa sổ đăng nhập";
/** Half past midnight on the twelfth in Hanoi, which is still the eleventh in UTC. */
const NOVEMBER = new Date("2026-11-11T17:30:00Z");

afterEach(() => {
  vitest.useRealTimers();
  vitest.restoreAllMocks();
  vitest.unstubAllGlobals();
});

/** This many hosts that each hold a sign-in, named so that their order by name is their number. */
const held = (count: number) => Object.fromEntries(Array.from({ length: count }, (_, at) => [`h${String(at + 1).padStart(2, "0")}.example`, NOVEMBER]));
const hostList = () => screen.getByRole("list", { name: LABEL });
const chips = () => within(hostList()).getAllByRole("listitem");
const said = () => chips().map((chip) => chip.textContent);
const more = (count: number) => screen.getByRole("button", { name: `+${count} máy chủ nữa` });
const part = () => screen.queryByTestId("browser-signed-in");
const none = () => screen.queryByTestId("browser-signed-in-none");

describe("the hosts of its own an agent's browser may still be signed in to", () => {
  const OWN = ["shop.example", "*.track.example", "bank.example", "mail.example", "docs.example", "news.example", "tax.example", "post.example", "maps.example", "wiki.example"];

  it("are each shown in the order of the agent's file, with the day the sign-in runs out on the viewer's calendar", async () => {
    const server = crew({ browser_hosts: OWN });
    server.browser.login.signedIn("coach", {
      "shop.example": NOVEMBER,
      // The last second of the year in Hanoi, and the first of the next.
      "www.bank.example": new Date("2026-12-31T16:59:59Z"),
      "mail.example": new Date("2026-12-31T17:00:00Z"),
    });
    show();

    await screen.findByTestId("browser-signed-in");
    expect(new Date().getTimezoneOffset()).toBe(-420);
    expect(said()).toEqual([
      "shop.example · đến 12/11/2026",
      "*.track.example · chưa thấy đăng nhập",
      "bank.example · đến 31/12/2026",
      "mail.example · đến 01/01/2027",
      "docs.example · chưa thấy đăng nhập",
      "news.example · chưa thấy đăng nhập",
      "tax.example · chưa thấy đăng nhập",
      "post.example · chưa thấy đăng nhập",
      "maps.example · chưa thấy đăng nhập",
      "wiki.example · chưa thấy đăng nhập",
    ]);
  });

  it("are all shown, however many, with no button for more", async () => {
    const server = crew({ browser_hosts: OWN });
    server.browser.login.signedIn("coach", {});
    show();

    await screen.findByTestId("browser-signed-in");
    expect(chips()).toHaveLength(10);
    expect(buttons()).toEqual([START]);
  });

  it("are muted where one holds no sign-in, and only there", async () => {
    const server = crew({ browser_hosts: ["shop.example", "*.track.example", "bank.example"] });
    server.browser.login.signedIn("coach", { "shop.example": NOVEMBER, "bank.example": NOVEMBER });
    show();

    await screen.findByTestId("browser-signed-in");
    expect(chips().map((chip) => chip.classList.contains("muted"))).toEqual([false, true, false]);
  });

  it("stand under a caveat on what the days are read from", async () => {
    const server = crew({ browser_hosts: ["shop.example"] });
    server.browser.login.signedIn("coach", { "shop.example": NOVEMBER });
    show();

    const caveat = await screen.findByText(CAVEAT);
    expect(hostList().compareDocumentPosition(caveat) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(part() as HTMLElement).getByText(LABEL)).toBeInTheDocument();
  });

  it("are drawn as the text they are, markup and all", async () => {
    const server = crew({ browser_hosts: ["<img src=x onerror=alert(1)>"] });
    server.browser.login.signedIn("coach", {});
    const { container } = show();

    await screen.findByTestId("browser-signed-in");
    expect(said()).toEqual(["<img src=x onerror=alert(1)> · chưa thấy đăng nhập"]);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("the hosts the browser of an agent with no list holds a sign-in for", () => {
  it("are shown eight at first, by name, with a button that says how many more there are", async () => {
    crew().browser.login.signedIn("coach", held(11));
    show();

    await screen.findByTestId("browser-signed-in");
    expect(said()).toEqual(["01", "02", "03", "04", "05", "06", "07", "08"].map((n) => `h${n}.example · đến 12/11/2026`));
    expect(buttons()).toEqual([START, "+3 máy chủ nữa"]);
    expect(more(3)).toBeEnabled();
    expect(screen.getByText(CAVEAT)).toBeInTheDocument();
  });

  it("are all shown once the button is pressed: it is gone, and the keyboard is on the list it filled", async () => {
    crew().browser.login.signedIn("coach", held(11));
    show();
    await screen.findByTestId("browser-signed-in");

    await userEvent.click(more(3));

    expect(chips()).toHaveLength(11);
    expect(said()[10]).toBe("h11.example · đến 12/11/2026");
    expect(buttons()).toEqual([START]);
    await waitFor(() => expect(hostList()).toHaveFocus());
  });

  it("does not take the keyboard before the button is pressed", async () => {
    crew().browser.login.signedIn("coach", held(11));
    show();

    await screen.findByTestId("browser-signed-in");
    await settle();
    expect(hostList()).not.toHaveFocus();
    expect(document.body).toHaveFocus();
  });

  it.each([
    [1, 1],
    [8, 8],
  ])("are all shown where there are %i, with no button", async (count, shown) => {
    crew().browser.login.signedIn("coach", held(count));
    show();

    await screen.findByTestId("browser-signed-in");
    expect(chips()).toHaveLength(shown);
    expect(buttons()).toEqual([START]);
  });

  it("have a button for the one more where there are nine", async () => {
    crew().browser.login.signedIn("coach", held(9));
    show();

    await screen.findByTestId("browser-signed-in");
    expect(chips()).toHaveLength(8);
    expect(buttons()).toEqual([START, "+1 máy chủ nữa"]);
  });

  it("stay all shown through the reads that follow the press, as the hosts change", async () => {
    const server = crew();
    server.browser.login.signedIn("coach", held(11));
    clock();
    show();
    await settle();
    await userEvent.click(more(3));
    expect(chips()).toHaveLength(11);

    server.browser.login.signedIn("coach", held(13));
    await pass(BROWSER_POLL_MS);

    expect(chips()).toHaveLength(13);
    expect(buttons()).toEqual([START]);
  });
});

describe("what the card is handed of the agent's own list", () => {
  it("decides how many are shown: a card told the agent has a list shows every host the server tells of", async () => {
    crew().browser.login.signedIn("coach", held(10));
    show({ savedHosts: ["shop.example"] });

    await screen.findByTestId("browser-signed-in");
    expect(chips()).toHaveLength(10);
    expect(buttons()).toEqual([START]);
  });

  it.each([
    ["an empty list", [] as string[]],
    ["no list, as from a server older than the key", undefined],
  ])("shows the first eight on a card handed %s, whatever the server tells of", async (_, savedHosts) => {
    const server = crew({ browser_hosts: Object.keys(held(10)) });
    server.browser.login.signedIn("coach", held(10));
    show({ savedHosts });

    await screen.findByTestId("browser-signed-in");
    expect(chips()).toHaveLength(8);
    expect(buttons()).toEqual([START, "+2 máy chủ nữa"]);
  });
});

describe("a browser with no host to tell of", () => {
  it("is said in one sentence where a browser closed on the profile and it holds no sign-in", async () => {
    crew().browser.login.closed("coach");
    show();

    expect((await screen.findByTestId("browser-signed-in-none")).textContent).toBe(NONE);
    expect(none()).toHaveClass("muted");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByText(LABEL)).not.toBeInTheDocument();
    // There is no day here to explain.
    expect(screen.queryByText(CAVEAT)).not.toBeInTheDocument();
    expect(part()).not.toBeInTheDocument();
  });

  it("is said too where every sign-in it held has run out", async () => {
    crew().browser.login.signedIn("coach", { "shop.example": new Date("2026-10-13T00:00:00Z") });
    show();

    expect(await screen.findByTestId("browser-signed-in-none")).toHaveTextContent(NONE);
  });

  it("has nothing drawn where there is nothing to tell: no browser ever closed on the profile", async () => {
    crew();
    show();

    await screen.findByRole("button", { name: START });
    expect(part()).not.toBeInTheDocument();
    expect(none()).not.toBeInTheDocument();
    expect(screen.queryByText(LABEL)).not.toBeInTheDocument();
    expect(screen.queryByText(CAVEAT)).not.toBeInTheDocument();
  });

  it("has nothing drawn on a machine that gives the agent no browser, whatever its profile holds", async () => {
    crew({ browser_hosts: ["shop.example"] }, { enabled: false }).browser.login.signedIn("coach", { "shop.example": NOVEMBER });
    show();

    await screen.findByTestId("browser-state");
    expect(part()).not.toBeInTheDocument();
    expect(none()).not.toBeInTheDocument();
  });

  it("has nothing drawn from a server that tells of no hosts, and the card is as it was", async () => {
    const server = crew({ browser_hosts: ["shop.example"] });
    server.browser.login.signedIn("coach", { "shop.example": NOVEMBER });
    server.browser.login.old = true;
    show();

    await screen.findByTestId("browser-state");
    expect(part()).not.toBeInTheDocument();
    expect(none()).not.toBeInTheDocument();
    expect(screen.queryByText(CAVEAT)).not.toBeInTheDocument();
    expect(buttons()).toEqual([]);
  });
});

describe("the signed-in hosts as the card is read again", () => {
  it("are not said aloud when they change: not the list, not the sentence for none, not the caveat", async () => {
    const server = crew();
    server.browser.login.signedIn("coach", held(2));
    clock();
    show();
    await settle();

    expect(saidAloud(hostList())).toBe(false);
    expect(saidAloud(chips()[0])).toBe(false);
    expect(saidAloud(screen.getByText(CAVEAT))).toBe(false);
    expect(saidAloud(screen.getByText(LABEL))).toBe(false);

    server.browser.login.signedIn("coach", {});
    await pass(BROWSER_POLL_MS);
    expect(saidAloud(none() as HTMLElement)).toBe(false);
  });

  it("follow the next read, with no request of their own", async () => {
    const server = crew({ browser_hosts: ["shop.example", "bank.example"] });
    server.browser.login.signedIn("coach", { "shop.example": NOVEMBER });
    clock();
    show();
    await settle();
    expect(said()).toEqual(["shop.example · đến 12/11/2026", "bank.example · chưa thấy đăng nhập"]);
    server.requests.length = 0;

    server.browser.login.signedIn("coach", { "bank.example": new Date("2027-03-01T05:00:00Z") });
    await pass(BROWSER_POLL_MS);

    expect(said()).toEqual(["shop.example · chưa thấy đăng nhập", "bank.example · đến 01/03/2027"]);
    expect(sent()).toEqual([`GET ${READ}`]);
  });

  it("are shown beside a browser that is up, and under a sign-in window that is open", async () => {
    const server = crew({ browser_hosts: ["shop.example"] });
    server.browser.login.signedIn("coach", { "pay.shop.example": NOVEMBER });
    server.browser.start("coach", [browserTab({ id: 1, label: "main" })]);
    clock();
    show();
    await settle();
    expect(screen.getByTestId("browser-tab-1")).toBeInTheDocument();
    expect(said()).toEqual(["shop.example · đến 12/11/2026"]);

    server.browser.route(OPEN, "POST", {});
    await pass(BROWSER_POLL_MS);

    const open = screen.getByTestId("browser-login-open");
    expect(said()).toEqual(["shop.example · đến 12/11/2026"]);
    expect(open.compareDocumentPosition(hostList()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
