import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi as vitest } from "vitest";
import { LinesField, TextField, NumberField, CheckField } from "./fields";

describe("LinesField", () => {
  it("renders the lines as text with newlines", () => {
    const onChange = vitest.fn();
    render(
      <LinesField
        label="Test Lines"
        value={["line1", "line2", "line3"]}
        onChange={onChange}
      />,
    );

    const textarea = screen.getByLabelText("Test Lines");
    expect(textarea).toHaveValue("line1\nline2\nline3");
  });

  it("resets the buffer when an external change occurs", () => {
    const onChange = vitest.fn();
    const { rerender } = render(
      <LinesField label="Test" value={["a", "b"]} onChange={onChange} />,
    );

    let textarea = screen.getByLabelText("Test");
    expect(textarea).toHaveValue("a\nb");

    // External change (e.g., from a revert)
    rerender(
      <LinesField label="Test" value={["c", "d"]} onChange={onChange} />,
    );

    textarea = screen.getByLabelText("Test");
    expect(textarea).toHaveValue("c\nd");
  });

  it("allows empty array as initial value", () => {
    const onChange = vitest.fn();
    render(
      <LinesField label="Test" value={[]} onChange={onChange} />,
    );

    const textarea = screen.getByLabelText("Test");
    expect(textarea).toHaveValue("");
  });

  it("renders with a custom row count", () => {
    const onChange = vitest.fn();
    render(
      <LinesField label="Test" value={["a"]} onChange={onChange} rows={10} />,
    );

    const textarea = screen.getByLabelText("Test") as HTMLTextAreaElement;
    expect(textarea.rows).toBe(10);
  });

  it("disables the textarea when disabled prop is true", () => {
    const onChange = vitest.fn();
    render(
      <LinesField label="Test" value={["a"]} onChange={onChange} disabled />,
    );

    const textarea = screen.getByLabelText("Test");
    expect(textarea).toBeDisabled();
  });

  it("shows hint text when provided", () => {
    const onChange = vitest.fn();
    render(
      <LinesField
        label="Test"
        value={["a"]}
        onChange={onChange}
        hint="One line per entry"
      />,
    );

    expect(screen.getByText("One line per entry")).toBeInTheDocument();
  });
});

describe("TextField", () => {
  it("renders with the provided value", () => {
    const onChange = vitest.fn();
    render(
      <TextField label="Name" value="Test" onChange={onChange} />,
    );

    expect(screen.getByLabelText("Name")).toHaveValue("Test");
  });

  it("is disabled when the disabled prop is true", () => {
    const onChange = vitest.fn();
    render(
      <TextField label="Name" value="" onChange={onChange} disabled />,
    );

    expect(screen.getByLabelText("Name")).toBeDisabled();
  });

  it("shows hint text when provided", () => {
    const onChange = vitest.fn();
    render(
      <TextField label="Name" value="" onChange={onChange} hint="Your name" />,
    );

    expect(screen.getByText("Your name")).toBeInTheDocument();
  });
});

describe("NumberField", () => {
  it("renders with the provided value", () => {
    const onChange = vitest.fn();
    render(
      <NumberField label="Count" value={42} onChange={onChange} />,
    );

    expect(screen.getByLabelText("Count")).toHaveValue(42);
  });

  it("converts an empty field to 0 instead of NaN", async () => {
    const onChange = vitest.fn();
    render(
      <NumberField label="Count" value={10} onChange={onChange} />,
    );

    const input = screen.getByLabelText("Count");
    await userEvent.clear(input);

    expect(onChange).toHaveBeenCalledWith(0);
  });

  it("respects min and step properties", () => {
    const onChange = vitest.fn();
    const input = render(
      <NumberField label="Cost" value={1} onChange={onChange} min={0} step={0.5} />,
    ).getByLabelText("Cost") as HTMLInputElement;

    expect(input.min).toBe("0");
    expect(input.step).toBe("0.5");
  });

  it("is disabled when the disabled prop is true", () => {
    const onChange = vitest.fn();
    render(
      <NumberField label="Count" value={0} onChange={onChange} disabled />,
    );

    expect(screen.getByLabelText("Count")).toBeDisabled();
  });
});

describe("CheckField", () => {
  it("renders as checked when the value is true", () => {
    const onChange = vitest.fn();
    render(
      <CheckField label="Autonomous" checked onChange={onChange} />,
    );

    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("renders as unchecked when the value is false", () => {
    const onChange = vitest.fn();
    render(
      <CheckField label="Autonomous" checked={false} onChange={onChange} />,
    );

    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("calls onChange with the new checked state when toggled", async () => {
    const onChange = vitest.fn();
    render(
      <CheckField label="Autonomous" checked={false} onChange={onChange} />,
    );

    const checkbox = screen.getByRole("checkbox");
    await userEvent.click(checkbox);

    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("is disabled when the disabled prop is true", () => {
    const onChange = vitest.fn();
    render(
      <CheckField label="Autonomous" checked={false} onChange={onChange} disabled />,
    );

    expect(screen.getByRole("checkbox")).toBeDisabled();
  });

  it("shows hint text when provided", () => {
    const onChange = vitest.fn();
    render(
      <CheckField
        label="Autonomous"
        checked={false}
        onChange={onChange}
        hint="Run without asking for approval"
      />,
    );

    expect(screen.getByText("Run without asking for approval")).toBeInTheDocument();
  });
});
