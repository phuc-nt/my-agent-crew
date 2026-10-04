import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { CanvasStatus } from "../../lib/canvas-machine";
import { landed, sent, startServer, stopServer, wait } from "../../test/canvas-hook";
import { editor, openPanel, saveState, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { refusingStorage } from "../../test/memory-storage";
import { statusText, stuckReason } from "./canvas-status";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

describe("the words for each status", () => {
  it.each<[CanvasStatus, string]>([
    ["loading", "Đang mở canvas…"],
    ["loadFailed", "Không mở được canvas."],
    ["gone", "Canvas đã bị xoá"],
    ["conflict", "Có hai bản khác nhau"],
    ["tooLarge", "Không lưu được: canvas vượt quá 512 KB"],
    ["full", "Không lưu được: hết chỗ lưu canvas trên máy chủ"],
    ["invalid", "Không lưu được: máy chủ không nhận nội dung này"],
    ["offline", "Mất kết nối, sẽ lưu khi có mạng"],
    ["serverDown", "Máy chủ không phản hồi, sẽ thử lại"],
    ["slow", "Mạng chậm, đang gửi lại"],
    ["saving", "Đang lưu…"],
    ["newer", "Có thay đổi mới"],
    ["unsaved", "Chưa lưu"],
    ["saved", "Đã lưu"],
  ])("says %s as “%s”", (status, text) => {
    expect(statusText(status)).toBe(text);
  });

  it.each<[CanvasStatus, string]>([
    ["conflict", "máy chủ có bản mới hơn"],
    ["tooLarge", "canvas vượt quá 512 KB"],
    ["full", "hết chỗ lưu canvas trên máy chủ"],
    ["invalid", "máy chủ không nhận nội dung này"],
    ["offline", "mất kết nối"],
    ["serverDown", "máy chủ không phản hồi"],
    ["slow", "mạng chậm"],
    ["gone", "canvas đã bị xoá"],
    ["saving", "chờ quá 5 giây"],
    ["unsaved", "chờ quá 5 giây"],
  ])("gives “%s” as why no version holds the text", (status, reason) => {
    expect(stuckReason(status)).toBe(reason);
  });

  it("names the limit a canvas too large was held to, in the size the person reads", () => {
    const MB = 1024 * 1024;

    expect(statusText("tooLarge", 4 * MB)).toBe("Không lưu được: canvas vượt quá 4 MB");
    expect(statusText("tooLarge", 2 * MB)).toBe("Không lưu được: canvas vượt quá 2 MB");
    expect(stuckReason("tooLarge", 4 * MB)).toBe("canvas vượt quá 4 MB");
    expect(stuckReason("tooLarge", 2 * MB)).toBe("canvas vượt quá 2 MB");
  });
});

describe("the save line", () => {
  it("follows a save from the keystroke until it lands", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    await openPanel();
    expect(saveState()).toBe("Đã lưu");
    const release = backend.canvas.holdNext("PUT", "reply");

    typeInto("ab");
    expect(saveState()).toBe("Chưa lưu");
    wait(1500);
    expect(saveState()).toBe("Đang lưu…");
    await act(() => release());
    await landed();

    expect(saveState()).toBe("Đã lưu");
  });

  it("says the server is not answering while the device has a network", async () => {
    backend.canvas.add({ content: "a" });
    await openPanel();
    backend.canvas.refuseNext("PUT", 503);

    typeInto("ab");
    wait(1500);
    await landed();

    expect(saveState()).toBe("Máy chủ không phản hồi, sẽ thử lại");
  });

  it("says the network is slow, not the server down, once a save has had no reply by its deadline", async () => {
    backend.canvas.add({ content: "a" });
    await openPanel();
    backend.canvas.holdNext("PUT");

    typeInto("ab");
    wait(1500);
    await landed();
    expect(saveState()).toBe("Đang lưu…");
    wait(30_000);
    await landed();
    expect(saveState()).toBe("Đang lưu…");
    wait(1);
    await landed();

    expect(saveState()).toBe("Mạng chậm, đang gửi lại");
  });

  it("says the save waits for a network while the device has none", async () => {
    backend.canvas.add({ content: "a" });
    await openPanel();
    backend.canvas.loseNext("PUT");

    typeInto("ab");
    wait(1500);
    await landed();
    vitest.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });

    expect(saveState()).toBe("Mất kết nối, sẽ lưu khi có mạng");
  });
});

describe("notices", () => {
  it("shows the largest canvases when the server is full, saves on its own no more, and saves on Cmd+S", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "a" });
    backend.canvas.add({ title: "Báo cáo dài", content: "x".repeat(2048) });
    await openPanel();
    backend.canvas.refuseNext("PUT", 507);

    typeInto("ab");
    wait(1500);
    await landed();

    const banner = screen.getByRole("alert");
    expect(within(banner).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "Báo cáo dài · 2 KB",
      "Ghi chú · 1 B",
    ]);
    expect(banner.textContent).toContain(vi.canvas.fullTitle);
    expect(banner.textContent).toContain(vi.canvas.fullHint);
    expect(saveState()).toBe("Không lưu được: hết chỗ lưu canvas trên máy chủ");

    typeInto("abc");
    wait(1500);
    await landed();
    expect(sent(backend, "PUT")).toHaveLength(1);

    fireEvent.keyDown(editor() as HTMLTextAreaElement, { key: "s", metaKey: true });
    await landed();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(saveState()).toBe("Đã lưu");
    expect(backend.canvas.content("a1")).toBe("abc");
  });

  it("shows the content of a version saved meanwhile nowhere but the conflict bar", async () => {
    backend.canvas.add({ title: "Ghi chú", content: "dòng một\ndòng hai" });
    const { container } = await openPanel();
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "BÍ-MẬT-409\ndòng hai", { author: "agent:ming" });

    typeInto("dòng của tôi\ndòng hai");
    wait(1500);
    await landed();

    expect(saveState()).toBe("Có hai bản khác nhau");
    expect(screen.getByRole("alert").textContent).toContain("Ming đã lưu v2 trong lúc bạn sửa.");
    expect(container.textContent).not.toContain("BÍ-MẬT-409");
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.showDiff }));
    expect(container.querySelector(".canvas-conflict")?.textContent).toContain("BÍ-MẬT-409");
    const outside = container.cloneNode(true) as HTMLElement;
    outside.querySelector(".canvas-conflict")?.remove();
    expect(outside.textContent).not.toContain("BÍ-MẬT-409");
  });

  it("says why a canvas asked to close has no saved version, and closes it anyway on request", async () => {
    backend.canvas.add({ content: "a" });
    backend.canvas.refuseNext("PUT", 422);
    const { props } = await openPanel({ stuck: true });
    expect(screen.queryByRole("alert")).toBeNull();

    typeInto("ab");
    wait(1500);
    await landed();

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Chưa lưu được: máy chủ không nhận nội dung này.");
    fireEvent.click(within(alert).getByRole("button", { name: vi.canvas.closeAnyway }));
    expect(props.onForceClose).toHaveBeenCalledTimes(1);
  });

  it("says closing anyway leaves the draft in this tab alone when this device could not keep it", async () => {
    backend.canvas.add({ content: "a" });
    backend.canvas.refuseNext("PUT", 422);
    refusingStorage();
    const { props } = await openPanel({ stuck: true });

    typeInto("ab");
    wait(1500);
    await landed();

    const stuck = screen
      .getAllByRole("alert")
      .find((alert) => alert.textContent?.includes(vi.canvas.stuck(vi.canvas.reasons.invalid))) as HTMLElement;
    expect(within(stuck).queryByRole("button", { name: vi.canvas.closeAnyway })).toBeNull();
    // The words themselves: the text is not lost by closing the panel, only with the tab.
    fireEvent.click(within(stuck).getByRole("button", { name: "Đóng, bản nháp chỉ còn trong tab này" }));
    expect(props.onForceClose).toHaveBeenCalledTimes(1);
  });
});
