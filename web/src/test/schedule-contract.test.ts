import { describe, expect, it } from "vitest";
import { applyAgentPatch, readSchedules } from "./schedule-contract";
import { fakeAgent } from "./fake-backend";

// The double stands in for the parser in every test of the agent editor, so what it takes
// and what it refuses is what those tests can prove. These are the rules of a script job.
const SOURCE = 'orders = tools.workspace_read(path="orders.json")\nprint(len(orders))\n';
const timed = { id: "sync", name: "Đồng bộ", cron: "40 6 * * *", enabled: true, skills: [] };
const ONE_ACTION = { error: "schedule needs exactly one of prompt / command / script" };
const THEN_ALONE = { error: "schedule takes then_prompt only beside script" };

describe("the action of a schedule, as the double reads it", () => {
  it("takes a prompt, a command or a script on its own", () => {
    for (const action of [{ prompt: "Tóm tắt" }, { command: "make backup" }, { script: SOURCE }]) {
      expect(readSchedules([{ ...timed, ...action }])).toHaveProperty("ok");
    }
  });

  it("refuses a row with none of the three, or with two of them", () => {
    const refused = [
      {},
      { prompt: "", command: "", script: "" },
      { prompt: null, command: null, script: null },
      { prompt: "Tóm tắt", command: "make backup" },
      { prompt: "Tóm tắt", script: SOURCE },
      { command: "make backup", script: SOURCE },
      { prompt: "Tóm tắt", command: "make backup", script: SOURCE },
    ];
    for (const action of refused) expect(readSchedules([{ ...timed, ...action }])).toEqual(ONE_ACTION);
  });

  it("takes a prompt to follow beside a script, and nowhere else", () => {
    expect(readSchedules([{ ...timed, script: SOURCE, then_prompt: "Tóm tắt đơn mới" }])).toHaveProperty("ok");
    expect(readSchedules([{ ...timed, prompt: "Tóm tắt", then_prompt: "Tóm tắt đơn mới" }])).toEqual(THEN_ALONE);
    expect(readSchedules([{ ...timed, command: "make backup", then_prompt: "Tóm tắt đơn mới" }])).toEqual(THEN_ALONE);
  });

  it("reads a prompt to follow that is null or absent as none, on any row", () => {
    for (const action of [{ prompt: "Tóm tắt" }, { command: "make backup" }, { script: SOURCE }]) {
      for (const none of [{}, { then_prompt: null }]) {
        const read = readSchedules([{ ...timed, ...action, ...none }]);
        expect(read).toMatchObject({ ok: [{ then_prompt: null }] });
      }
    }
  });

  it("still refuses a key it does not know, and the derived kind among them", () => {
    expect(readSchedules([{ ...timed, script: SOURCE, kind: "script" }])).toEqual({ error: 'schedule has unknown keys ["kind"]' });
    expect(readSchedules([{ ...timed, script: SOURCE, then: "Tóm tắt" }])).toEqual({ error: 'schedule has unknown keys ["then"]' });
  });

  // Timing is asked before the action, as before: a script row is no way round it.
  it("still asks a script row for exactly one timing", () => {
    const { cron: _cron, ...untimed } = timed;
    expect(readSchedules([{ ...untimed, script: SOURCE }])).toEqual({ error: "schedule needs exactly one of cron / every" });
    expect(readSchedules([{ ...timed, every: "6h", script: SOURCE }])).toEqual({ error: "schedule needs exactly one of cron / every" });
  });
});

describe("what the double declares back", () => {
  it("is every row with both script keys, null where the row has no script", () => {
    const read = readSchedules([
      { ...timed, script: SOURCE, then_prompt: "Tóm tắt đơn mới" },
      { ...timed, id: "quiet", script: SOURCE },
      { ...timed, id: "brief", prompt: "Tóm tắt" },
      { ...timed, id: "backup", command: "make backup" },
    ]);
    if (!("ok" in read)) throw new Error(read.error);
    expect(read.ok.map(({ id, prompt, command, script, then_prompt }) => ({ id, prompt, command, script, then_prompt }))).toEqual([
      { id: "sync", prompt: null, command: null, script: SOURCE, then_prompt: "Tóm tắt đơn mới" },
      { id: "quiet", prompt: null, command: null, script: SOURCE, then_prompt: null },
      { id: "brief", prompt: "Tóm tắt", command: null, script: null, then_prompt: null },
      { id: "backup", prompt: null, command: "make backup", script: null, then_prompt: null },
    ]);
    // The script is kept as written: its line breaks are the script.
    expect(read.ok[0].script).toBe(SOURCE);
  });

  it("names each job's kind by the action its row has", () => {
    const patched = applyAgentPatch(fakeAgent, {
      schedules: [
        { ...timed, script: SOURCE, then_prompt: "Tóm tắt đơn mới" },
        { ...timed, id: "brief", prompt: "Tóm tắt" },
        { ...timed, id: "backup", command: "make backup" },
      ],
    });
    if (!("ok" in patched)) throw new Error(patched.error);
    expect(patched.ok.schedules.map((job) => [job.id, job.kind])).toEqual([
      ["sync", "script"],
      ["brief", "prompt"],
      ["backup", "command"],
    ]);
    // The derived kind is on the jobs, never on the rows the file declares.
    for (const row of patched.ok.declared.schedules) expect(row).not.toHaveProperty("kind");
    expect(patched.ok.schedules[0]).toMatchObject({ script: SOURCE, then_prompt: "Tóm tắt đơn mới" });
  });

  it("refuses the whole patch for one row with two actions, leaving the agent as it was", () => {
    const patched = applyAgentPatch(fakeAgent, {
      schedules: [{ ...timed, id: "brief", prompt: "Tóm tắt" }, { ...timed, prompt: "Tóm tắt", script: SOURCE }],
    });
    expect(patched).toEqual(ONE_ACTION);
    expect(fakeAgent.declared.schedules).toEqual([]);
  });
});

describe("the two script switches, as the double reads them", () => {
  it("takes each value the file takes, and answers with it", () => {
    for (const value of ["none", "read_only", "gated"])
      expect(applyAgentPatch(fakeAgent, { script_calls: value })).toMatchObject({ ok: { script_calls: value } });
    for (const value of [true, false])
      expect(applyAgentPatch(fakeAgent, { script_llm: value })).toMatchObject({ ok: { script_llm: value } });
  });

  it("refuses anything else: a label, another case, a string for the boolean", () => {
    for (const value of ["Gated", "off", "", true, 1])
      expect(applyAgentPatch(fakeAgent, { script_calls: value })).toEqual({ error: "script_calls must be none, read_only or gated" });
    for (const value of ["false", "no", 0, "none"])
      expect(applyAgentPatch(fakeAgent, { script_llm: value })).toEqual({ error: "script_llm must be true or false" });
  });

  it("reads a cleared key back as what the crew runs an agent as", () => {
    const set = { ...fakeAgent, script_calls: "gated" as const, script_llm: false };
    expect(applyAgentPatch(set, { script_calls: null, script_llm: null })).toMatchObject({ ok: { script_calls: "read_only", script_llm: true } });
    // A patch that names neither leaves both as they were.
    expect(applyAgentPatch(set, { name: "Khác" })).toMatchObject({ ok: { script_calls: "gated", script_llm: false } });
  });
});
