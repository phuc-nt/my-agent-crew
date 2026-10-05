import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentInfo } from "../../api/types";
import { vi } from "../../i18n/vi";
import { FakeBackend, fakeAgent } from "../../test/fake-backend";
import { AgentEditor } from "./agent-editor";

const t = vi.editor;
const BIG = { provider: "openrouter", model: "big" };
let backend: FakeBackend;

function open(shown: AgentInfo, providers = ["fake", "openrouter"]) {
  backend = new FakeBackend();
  backend.agents = [shown];
  vitest.stubGlobal("fetch", backend.fetch);
  render(
    <AgentEditor agent={shown} agents={[shown]} tools={[]} providers={providers} onBack={() => {}} onChanged={() => {}} />,
  );
}

const block = () => within(screen.getByTestId("escalation-route"));
const providerBox = () => block().getByLabelText(`${t.escalationRoute}: ${t.provider}`);
const modelBox = () => block().getByLabelText(`${t.escalationRoute}: ${t.model}`);
const saveButton = () => screen.getByRole("button", { name: t.save });
const patches = () => backend.requests.filter((r) => r.method === "PATCH").map((r) => r.body);

describe("the escalation route of an agent that names none", () => {
  it("says a stuck turn stops as before, and offers to set one", () => {
    open(fakeAgent);

    expect(block().getByText(t.escalationRouteHint)).toBeInTheDocument();
    expect(block().getByTestId("escalation-route-none")).toHaveTextContent(t.escalationRouteNone);
    expect(block().queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("is set by adding a row on a real provider, typing the model and saving", async () => {
    open(fakeAgent);
    await userEvent.click(block().getByRole("button", { name: t.addEscalationRoute }));

    // `fake` only echoes the prompt back; a new row starts on a provider that can answer.
    expect(providerBox()).toHaveValue("openrouter");
    expect(block().queryByTestId("escalation-route-none")).not.toBeInTheDocument();
    await userEvent.type(modelBox(), "big");
    await userEvent.click(saveButton());

    await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
    expect(patches()).toEqual([{ profile: { escalation_route: BIG } }]);
    expect(modelBox()).toHaveValue("big");
  });

  it("asks for the model when a save is tried, not the moment the row is added", async () => {
    open(fakeAgent);
    await userEvent.click(block().getByRole("button", { name: t.addEscalationRoute }));

    expect(block().queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("save-held")).not.toBeInTheDocument();

    await userEvent.click(saveButton());
    expect(block().getByRole("alert")).toHaveTextContent(t.escalationModelMissing);
    expect(modelBox()).toHaveAttribute("aria-invalid", "true");
    expect(modelBox()).toHaveAccessibleDescription(t.escalationModelMissing);
    expect(saveButton()).toBeDisabled();
    expect(patches()).toEqual([]);

    await userEvent.type(modelBox(), "big");
    expect(block().queryByRole("alert")).not.toBeInTheDocument();
    expect(modelBox()).not.toHaveAttribute("aria-invalid");
    await userEvent.click(saveButton());
    await waitFor(() => expect(patches()).toEqual([{ profile: { escalation_route: BIG } }]));
  });

  it("is refused, under its own row, while it is one of the routes above", async () => {
    open(fakeAgent);
    await userEvent.click(block().getByRole("button", { name: t.addEscalationRoute }));
    await userEvent.selectOptions(providerBox(), "fake");
    await userEvent.type(modelBox(), "echo");

    expect(block().getByRole("alert")).toHaveTextContent(t.escalationSameAsRoute);
    expect(saveButton()).toBeDisabled();

    await userEvent.type(modelBox(), "-big");
    expect(block().queryByRole("alert")).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });
});

describe("the escalation route of an agent that names one", () => {
  const named = { ...fakeAgent, escalation_route: BIG };

  it("shows it, and offers a provider the crew did not build only because the file names it", () => {
    open(named, ["fake"]);

    expect(providerBox()).toHaveValue("openrouter");
    expect(modelBox()).toHaveValue("big");
    expect(within(providerBox()).getAllByRole("option").map((o) => o.textContent)).toEqual(["fake", "openrouter"]);
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });

  it("is cleared with null when it is taken away", async () => {
    open(named);
    await userEvent.click(block().getByRole("button", { name: t.removeEscalationRoute }));

    expect(block().getByTestId("escalation-route-none")).toBeInTheDocument();
    await userEvent.click(saveButton());

    await waitFor(() => expect(screen.getByText(t.clean)).toBeInTheDocument());
    expect(patches()).toEqual([{ profile: { escalation_route: null } }]);
  });

  it("is checked again when a route above is changed onto it", async () => {
    open(named);
    const [ownModel] = within(screen.getByTestId("route-editor")).getAllByLabelText(t.model);
    const [ownProvider] = within(screen.getByTestId("route-editor")).getAllByLabelText(t.provider);
    await userEvent.selectOptions(ownProvider, "openrouter");
    await userEvent.clear(ownModel);
    await userEvent.type(ownModel, "big");

    expect(block().getByRole("alert")).toHaveTextContent(t.escalationSameAsRoute);
    expect(saveButton()).toBeDisabled();
    expect(patches()).toEqual([]);
  });

  it("shows what the server said when it refuses the route, and keeps what was typed", async () => {
    open(named);
    backend.refuseEdit = "Tuyến leo thang openrouter:huge không dùng được (thiếu khoá API cho provider).";
    await userEvent.clear(modelBox());
    await userEvent.type(modelBox(), "huge");
    await userEvent.click(saveButton());

    expect(await screen.findByText(t.saveFailed(backend.refuseEdit))).toBeInTheDocument();
    expect(modelBox()).toHaveValue("huge");
  });

  it("cannot be changed on an agent a kit defines", () => {
    open({ ...named, editable: false });

    expect(providerBox()).toBeDisabled();
    expect(modelBox()).toBeDisabled();
    expect(block().getByRole("button", { name: t.removeEscalationRoute })).toBeDisabled();
  });
});

describe("an agent reported by a server that does not know the key", () => {
  it("has no escalation route, and nothing to save", () => {
    const { escalation_route: _unknown, ...older } = fakeAgent;
    open(older as AgentInfo);

    expect(block().getByTestId("escalation-route-none")).toBeInTheDocument();
    expect(screen.getByText(t.clean)).toBeInTheDocument();
  });
});
