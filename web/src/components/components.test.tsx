import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeApproval } from "../test/fake-backend";
import { questionPending, toolPending } from "../test/pending";
import { ApprovalBar } from "./approval-bar";
import { ApprovalHistory } from "./approval-history";
import { BudgetIndicator, formatUsd } from "./budget-indicator";
import { Composer } from "./composer";
import { ConversationList } from "./conversation-list";
import { QuestionCard } from "./question-card";
import { formatClock } from "./run-timeline";
import { ToolCallCard, summarizeArguments } from "./tool-call-card";

describe("ToolCallCard", () => {
  it("shows name, status label and toggles the output", async () => {
    render(
      <ToolCallCard
        item={{ kind: "tool", id: "tc", name: "read_file", arguments: { path: "a.txt" }, output: "body text", status: "done" }}
      />,
    );
    expect(screen.getByText(/read_file/)).toBeInTheDocument();
    expect(screen.getByText(vi.toolDone)).toBeInTheDocument();
    expect(screen.queryByText("body text")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.showOutput }));
    expect(screen.getByText("body text")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.hideOutput }));
    expect(screen.queryByText("body text")).not.toBeInTheDocument();
  });

  it("hides the output toggle while a tool is still running", () => {
    render(<ToolCallCard item={{ kind: "tool", id: "tc", name: "x", arguments: {}, output: null, status: "running" }} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(vi.toolRunning)).toBeInTheDocument();
  });

  it("summarizes arguments compactly and truncates long values", () => {
    expect(summarizeArguments({ path: "a", n: 2 })).toBe("path=a, n=2");
    expect(summarizeArguments({ text: "x".repeat(80) })).toBe(`text=${"x".repeat(57)}…`);
  });

  // Runs recorded before the store kept arguments as a mapping hold one string
  // instead. Walking it by index showed a pair per character; the line itself is
  // the closest thing to the truth those runs still have.
  it("shows an argument line recorded as one string as it stands", () => {
    expect(summarizeArguments("{'path': 'memory/note.md'}")).toBe("{'path': 'memory/note.md'}");
  });
});

describe("BudgetIndicator", () => {
  it("shows spent against the cap on the pill and the bar in the card it opens", async () => {
    render(<BudgetIndicator spentUsd={0.25} capUsd={1} unknownCostCalls={0} />);
    const pill = screen.getByTestId("budget");
    expect(pill).toHaveTextContent(`${vi.spent("$0.25", "$1.00")} (25%)`);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();

    await userEvent.click(pill);
    const card = screen.getByRole("dialog", { name: vi.budgetCard.title });
    expect(within(card).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(card).toHaveTextContent(vi.budgetCard.left("$0.75"));
    expect(screen.queryByText(/\? \d/)).not.toBeInTheDocument();

    // Escape and a click outside both put the card away; a click inside does not.
    await userEvent.click(within(card).getByText(vi.budgetCard.spent));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(pill);
    await userEvent.click(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // The app folds its activity panel on Escape too; closing a card must not do that as
  // well, and the keyboard user lands back on the pill they opened it from.
  it("keeps Escape to itself and hands focus back to the pill", async () => {
    const appEscape = vitest.fn();
    window.addEventListener("keydown", appEscape);
    render(<BudgetIndicator spentUsd={0.25} capUsd={1} unknownCostCalls={0} />);
    const pill = screen.getByTestId("budget");
    await userEvent.click(pill);
    expect(pill).toHaveAttribute("aria-controls", screen.getByRole("dialog").id);

    await userEvent.keyboard("{Escape}");
    window.removeEventListener("keydown", appEscape);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(appEscape).not.toHaveBeenCalled();
    expect(pill).toHaveFocus();
  });

  it("marks unlimited caps and unknown-cost calls", async () => {
    render(<BudgetIndicator spentUsd={0} capUsd={0} unknownCostCalls={3} />);
    expect(screen.getByTestId("budget")).toHaveTextContent(vi.unlimited);
    expect(screen.getByTitle(vi.unknownCost(3))).toHaveTextContent("? 3");

    await userEvent.click(screen.getByTestId("budget"));
    const card = screen.getByRole("dialog");
    expect(within(card).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(card).toHaveTextContent(vi.budgetCard.unknownValue(3));
  });

  it("flags an exhausted budget", () => {
    render(<BudgetIndicator spentUsd={1.2} capUsd={1} unknownCostCalls={0} />);
    expect(screen.getByTestId("budget")).toHaveClass("over");
  });

  it("formats sub-cent amounts with more precision", () => {
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(1.5)).toBe("$1.50");
    expect(formatUsd(0)).toBe("$0.00");
  });
});

describe("ApprovalBar", () => {
  it("names the tool and reports the decision", async () => {
    const onDecide = vitest.fn();
    render(
      <ApprovalBar pending={toolPending({ name: "write_file", arguments: { path: "x" } })} busy={false} onDecide={onDecide} />,
    );
    expect(screen.getByText(vi.approvalTitle("write_file"))).toBeInTheDocument();
    expect(screen.getByText("path=x")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.deny }));
    await userEvent.click(screen.getByRole("button", { name: vi.approve }));
    expect(onDecide.mock.calls).toEqual([[false], [true]]);
  });

  it("shows why an autonomous conversation stopped, and nothing when it did not", () => {
    const reason = "khớp mẫu cần duyệt: `rm -rf`";
    const { rerender } = render(
      <ApprovalBar pending={toolPending({ name: "shell_run", reason })} busy={false} onDecide={() => undefined} />,
    );
    expect(screen.getByText(reason)).toBeInTheDocument();
    rerender(
      <ApprovalBar pending={toolPending({ name: "shell_run" })} busy={false} onDecide={() => undefined} />,
    );
    expect(screen.queryByText(reason)).not.toBeInTheDocument();
  });

  it("disables every button while the resumed turn is running", () => {
    render(
      <ApprovalBar pending={toolPending({ name: "x" })} busy onDecide={() => undefined} onAlways={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: vi.approve })).toBeDisabled();
    expect(screen.getByRole("button", { name: vi.alwaysAllow })).toBeDisabled();
    expect(screen.getByRole("button", { name: vi.deny })).toBeDisabled();
  });

  it("shows the deadline of an unanswered request and offers to always allow the tool", async () => {
    const onDecide = vitest.fn();
    const onAlways = vitest.fn();
    const expiresAt = "2026-09-20T03:10:00Z";
    render(
      <ApprovalBar
        pending={toolPending({ name: "write_file", expiresAt })}
        busy={false}
        onDecide={onDecide}
        onAlways={onAlways}
      />,
    );
    expect(screen.getByText(vi.approvalDeadline(formatClock(expiresAt)))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.alwaysAllow }));
    expect(onAlways).toHaveBeenCalledTimes(1);
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("hides the always-allow button and the deadline when neither is available", () => {
    render(<ApprovalBar pending={toolPending({ name: "x" })} busy={false} onDecide={() => undefined} />);
    expect(screen.queryByRole("button", { name: vi.alwaysAllow })).not.toBeInTheDocument();
    expect(screen.queryByText(/tự từ chối/)).not.toBeInTheDocument();
  });
});

describe("QuestionCard", () => {
  it("shows what was asked and sends typed words as the answer", async () => {
    const onAnswer = vitest.fn();
    render(<QuestionCard pending={questionPending()} busy={false} onAnswer={onAnswer} />);
    expect(screen.getByText("Dời hạn sang thứ sáu?")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox"), "  dời sang thứ bảy  ");
    await userEvent.click(screen.getByRole("button", { name: vi.questionSend }));
    expect(onAnswer).toHaveBeenCalledWith("dời sang thứ bảy");
  });

  it("offers each choice as a button that answers with its own words", async () => {
    const onAnswer = vitest.fn();
    const pending = questionPending({ options: ["có", "không"] });
    render(<QuestionCard pending={pending} busy={false} onAnswer={onAnswer} />);
    await userEvent.click(screen.getByRole("button", { name: "không" }));
    expect(onAnswer).toHaveBeenCalledWith("không");
  });

  it("keeps the text box even when choices are offered", () => {
    // The server takes any wording, and the answer worth giving is often not on the list.
    render(
      <QuestionCard pending={questionPending({ options: ["có"] })} busy={false} onAnswer={() => undefined} />,
    );
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("refuses to send an empty answer", async () => {
    const onAnswer = vitest.fn();
    render(<QuestionCard pending={questionPending()} busy={false} onAnswer={onAnswer} />);
    expect(screen.getByRole("button", { name: vi.questionSend })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "   ");
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("says the deadline means a default, not a refusal", () => {
    // A tool nobody answers is refused; a question nobody answers returns its default and
    // the agent carries on. Telling the person the wrong one would misdirect their urgency.
    const expiresAt = "2026-09-23T03:10:00Z";
    render(
      <QuestionCard pending={questionPending({ expiresAt })} busy={false} onAnswer={() => undefined} />,
    );
    expect(screen.getByText(vi.questionDeadline(formatClock(expiresAt)))).toBeInTheDocument();
  });

  it("disables every way of answering while the resumed turn runs", () => {
    render(
      <QuestionCard pending={questionPending({ options: ["có"] })} busy onAnswer={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: "có" })).toBeDisabled();
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});

describe("ApprovalHistory", () => {
  afterEach(() => vitest.unstubAllGlobals());

  const history = (backend: FakeBackend) => {
    vitest.stubGlobal("fetch", backend.fetch);
    render(<ApprovalHistory agentName={() => "HLV"} onOpenConversation={() => undefined} refreshKey={0} />);
    return screen.findByTestId("approval-history");
  };
  const limits = (backend: FakeBackend) =>
    backend.requests.filter((r) => r.path.startsWith("/approvals")).map((r) => new URLSearchParams(r.path.split("?")[1]).get("limit"));
  /** Waits for the list to hold `count` rows, then checks them as list items once: a role
   *  query over hundreds of rows on every poll outlasts the timeout on a busy machine. */
  const rowsReach = async (list: HTMLElement, count: number) => {
    await vitest.waitFor(() => expect(list.querySelectorAll(":scope > li")).toHaveLength(count));
    expect(within(list).getAllByRole("listitem")).toHaveLength(count);
  };
  /** The "Xem thêm" button, found by its text, which is its name: a role query weighs the
   *  name of every row's button, and past a few hundred rows outlasts the timeout on CI. */
  const showMore = () => screen.getByText(vi.showMore, { selector: "button" });
  const noShowMore = () => expect(screen.queryByText(vi.showMore, { selector: "button" })).not.toBeInTheDocument();

  it("reads a question as what was asked, what it offered and what came back", async () => {
    const backend = new FakeBackend();
    backend.approvals = [
      fakeApproval({
        id: "q1",
        tool_name: "ask_user",
        kind: "question",
        arguments: { question: "Dời hạn sang thứ sáu?", options: ["có", "không"] },
        options: ["có", "không"],
        status: "answered",
        answer: "không",
      }),
    ];
    const item = within(await history(backend)).getByRole("listitem");
    expect(item).toHaveTextContent("Dời hạn sang thứ sáu?");
    expect(within(item).getByText("có")).toBeInTheDocument();
    expect(within(item).getByText("không", { selector: ".approval-option" })).toBeInTheDocument();
    expect(item).toHaveTextContent(vi.approvalAnswer("không"));
    expect(item).not.toHaveTextContent("question=");
  });

  it("fetches a bigger page on 'Xem thêm' until the server runs out or its ceiling is hit", async () => {
    const backend = new FakeBackend();
    backend.approvals = Array.from({ length: 260 }, (_, i) => fakeApproval({ id: `a${i}` }));
    const list = await history(backend);
    expect(within(list).getAllByRole("listitem")).toHaveLength(50);

    await userEvent.click(showMore());
    await rowsReach(list, 200);
    await userEvent.click(showMore());
    await rowsReach(list, 260);
    // 260 of a possible 500: the whole history is on screen, so there is nothing more to ask for.
    noShowMore();
    expect(limits(backend)).toEqual(["50", "200", "500"]);
  });

  it("stops offering more at the server's ceiling even when that page is full", async () => {
    const backend = new FakeBackend();
    backend.approvals = Array.from({ length: 520 }, (_, i) => fakeApproval({ id: `a${i}` }));
    const list = await history(backend);
    await userEvent.click(showMore());
    await rowsReach(list, 200);
    await userEvent.click(showMore());
    await rowsReach(list, 500);
    noShowMore();
  });

  it("keeps the rows already read when a bigger page fails, says so and asks again", async () => {
    const backend = new FakeBackend();
    backend.approvals = Array.from({ length: 260 }, (_, i) => fakeApproval({ id: `a${i}` }));
    let refuse = false;
    const list = await history(backend);
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      refuse ? Promise.resolve(new Response("{}", { status: 500 })) : backend.fetch(input, init),
    );

    refuse = true;
    await userEvent.click(showMore());
    expect(await screen.findByText(vi.loadFailed)).toBeInTheDocument();
    expect(within(list).getAllByRole("listitem")).toHaveLength(50);

    refuse = false;
    await userEvent.click(showMore());
    await rowsReach(list, 200);
    expect(screen.queryByText(vi.loadFailed)).not.toBeInTheDocument();
  });

  it("hands focus to the first new row when the last page takes the button away", async () => {
    const backend = new FakeBackend();
    backend.approvals = Array.from({ length: 120 }, (_, i) => fakeApproval({ id: `a${i}` }));
    const list = await history(backend);

    await userEvent.click(screen.getByRole("button", { name: vi.showMore }));

    await rowsReach(list, 120);
    expect(screen.queryByRole("button", { name: vi.showMore })).not.toBeInTheDocument();
    expect(within(list).getAllByRole("listitem")[50]).toHaveFocus();
  });

  it("offers no more when the first page is already short", async () => {
    const backend = new FakeBackend();
    backend.approvals = [fakeApproval(), fakeApproval({ id: "ap2" })];
    await history(backend);
    expect(screen.queryByRole("button", { name: vi.showMore })).not.toBeInTheDocument();
  });

  it("opens a tool row's full arguments from under its summary", async () => {
    const backend = new FakeBackend();
    const command = `python scripts/migrate.py ${"--table events ".repeat(6)}--dry-run`;
    backend.approvals = [fakeApproval({ tool_name: "shell_run", arguments: { command } })];
    const item = within(await history(backend)).getByRole("listitem");
    expect(item).not.toHaveTextContent("--dry-run");
    await userEvent.click(within(item).getByRole("button", { name: vi.argumentsMore }));
    expect(within(item).getByTestId("args-detail")).toHaveTextContent(command);
  });
});

describe("Composer", () => {
  it("sends trimmed text on Enter and keeps newlines on Shift+Enter", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy={false} onSend={onSend} onStop={() => undefined} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "line one{Shift>}{Enter}{/Shift}line two ");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("line one\nline two");
    expect(box).toHaveValue("");
  });

  it("ignores empty submissions and disables send when empty", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy={false} onSend={onSend} onStop={() => undefined} />);
    expect(screen.getByRole("button", { name: vi.send })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "   {Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("offers a stop button while busy and blocks input while disabled", async () => {
    const onStop = vitest.fn();
    const { rerender } = render(<Composer disabled={false} busy onSend={() => undefined} onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: vi.stop }));
    expect(onStop).toHaveBeenCalled();
    rerender(<Composer disabled busy={false} onSend={() => undefined} onStop={onStop} />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("lets an input method commit a word with Enter instead of sending half of it", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy={false} onSend={onSend} onStop={() => undefined} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "Vieejt");
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("Vieejt");
  });

  // Safari ends the composition first and then delivers the committing Enter, marked
  // only by the IME's keyCode.
  it("does not send on the Enter that Safari delivers after the composition ends", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy={false} onSend={onSend} onStop={() => undefined} />);
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "Vieejt");
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229, isComposing: false });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter", keyCode: 13 });
    expect(onSend).toHaveBeenCalledWith("Vieejt");
  });

  it("names the agent in the empty box but keeps one stable name for the field", () => {
    render(<Composer disabled={false} busy={false} agentName="Trợ lý" onSend={() => undefined} onStop={() => undefined} />);
    const box = screen.getByRole("textbox", { name: vi.composerPlaceholder });
    expect(box).toHaveAttribute("placeholder", vi.composerPlaceholderFor("Trợ lý"));
  });

  it("prefills the draft handed in from a suggestion", () => {
    render(<Composer disabled={false} busy={false} draft="gợi ý" onSend={() => undefined} onStop={() => undefined} />);
    expect(screen.getByRole("textbox")).toHaveValue("gợi ý");
  });

  it("still sends on Enter while busy: the box is never locked, only Stop is offered beside it", async () => {
    const onSend = vitest.fn();
    render(<Composer disabled={false} busy onSend={onSend} onStop={() => undefined} />);
    await userEvent.type(screen.getByRole("textbox"), "chen ngang{Enter}");
    expect(onSend).toHaveBeenCalledWith("chen ngang");
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("labels the send button by what a busy send will do: queue a plain message, steer a /steer one", () => {
    const { rerender } = render(<Composer disabled={false} busy onSend={() => undefined} onStop={() => undefined} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "việc bình thường" } });
    expect(screen.getByRole("button", { name: vi.sendQueue })).toBeInTheDocument();

    rerender(<Composer disabled={false} busy onSend={() => undefined} onStop={() => undefined} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "/steer chen vao" } });
    expect(screen.getByRole("button", { name: vi.sendSteer })).toBeInTheDocument();
  });

  it("offers both Stop and send while busy with text typed, but only Stop once the box is empty", () => {
    render(<Composer disabled={false} busy onSend={() => undefined} onStop={() => undefined} />);
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.sendQueue })).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "chen ngang" } });
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.sendQueue })).toBeInTheDocument();
  });

  it("hides Stop when the caller says the busy turn cannot be stopped from here", () => {
    render(<Composer disabled={false} busy stoppable={false} onSend={() => undefined} onStop={() => undefined} />);
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();
  });

  it("prepends restored text to whatever is already in the box, then focuses it", async () => {
    const { rerender } = render(
      <Composer disabled={false} busy={false} onSend={() => undefined} onStop={() => undefined} />,
    );
    const box = screen.getByRole("textbox");
    await userEvent.type(box, "chua gui");
    box.blur();

    rerender(
      <Composer
        disabled={false}
        busy={false}
        restore={{ nonce: 1, text: "lay lai" }}
        onSend={() => undefined}
        onStop={() => undefined}
      />,
    );
    expect(box).toHaveValue("lay lai\n\nchua gui");
    await waitFor(() => expect(box).toHaveFocus());
  });

  it("restores alone with no join when the box was empty", async () => {
    render(
      <Composer
        disabled={false}
        busy={false}
        restore={{ nonce: 1, text: "lay lai" }}
        onSend={() => undefined}
        onStop={() => undefined}
      />,
    );
    const box = screen.getByRole("textbox");
    expect(box).toHaveValue("lay lai");
    await waitFor(() => expect(box).toHaveFocus());
  });
});

describe("ConversationList", () => {
  const base = {
    id: "c1", agent_id: "default", channel: "", title: "Web", created_at: "", updated_at: "",
    autonomous: false, cost_cap_usd: 1, skills: [], auto_approve: [], parent_call_id: "", spent_usd: 0, unknown_cost_calls: 0,
    status: "idle" as const, over_budget: false, summary: "",
  };

  it("tags conversations that come from a channel and leaves web ones plain", () => {
    render(
      <ConversationList
        conversations={[base, { ...base, id: "c2", channel: "telegram:42", title: "Telegram · 2026-09-19" }]}
        activeId="c1"
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getAllByText("Telegram")).toHaveLength(1);
    expect(screen.getByText("Web").parentElement?.querySelector(".channel-tag")).toBeNull();
  });

  it("shows the recap under a conversation that has one and nothing under one that does not", () => {
    render(
      <ConversationList
        conversations={[{ ...base, summary: "Đã dựng xong bản nháp." }, { ...base, id: "c2", title: "Trống" }]}
        activeId="c1"
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("Đã dựng xong bản nháp.")).toBeInTheDocument();
    expect(screen.getByText("Trống").parentElement?.querySelector(".conversation-summary")).toBeNull();
  });
});

describe("vi labels", () => {
  it("names run sources and channels in Vietnamese", () => {
    expect(vi.runSource("chat")).toBe("trò chuyện");
    expect(vi.runSource("telegram")).toBe("Telegram");
    expect(vi.runSource("job:coach/brief")).toBe("lịch coach/brief");
    expect(vi.channelName("telegram:42")).toBe("Telegram");
    expect(vi.channelName("slack:x")).toBe("slack");
  });
});
