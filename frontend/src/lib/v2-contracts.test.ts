import { describe, expect, it } from "vitest";
import {
  getV2DepartmentLabel,
  getV2LifecycleLabel,
  isStaffAvailabilityState,
  isStaffEmploymentState,
  isV2DepartmentId,
  isV2LifecycleStatus,
  parseV2TicketContract,
  readTicketVersion,
  staffAvailabilityLabels,
  staffAvailabilityStates,
  staffEmploymentLabels,
  staffEmploymentStates,
  v2DepartmentIds,
  v2DepartmentLabels,
  v2LifecycleLabels,
  v2LifecycleStatuses,
} from "./v2-contracts";

const v2Ticket = {
  schemaVersion: "v2",
  workflowVersion: "v2",
  taxonomyVersion: "v2",
  categoryId: "general_complaints",
  status: "received",
};

describe("V2 shared contracts", () => {
  it("keeps all approved V2 categories, statuses, and Staff states", () => {
    expect(v2DepartmentIds).toHaveLength(8);
    expect(v2LifecycleStatuses).toHaveLength(9);
    expect(staffEmploymentStates).toHaveLength(6);
    expect(staffAvailabilityStates).toHaveLength(4);
    expect(v2DepartmentIds.every(isV2DepartmentId)).toBe(true);
    expect(v2LifecycleStatuses.every(isV2LifecycleStatus)).toBe(true);
    expect(staffEmploymentStates.every(isStaffEmploymentState)).toBe(true);
    expect(staffAvailabilityStates.every(isStaffAvailabilityState)).toBe(true);
  });

  it("has complete English and Myanmar labels", () => {
    for (const id of v2DepartmentIds) {
      expect(v2DepartmentLabels[id].en).toBeTruthy();
      expect(v2DepartmentLabels[id].my).toMatch(/[\u1000-\u109f]/u);
      expect(getV2DepartmentLabel(id, "en")).toBe(v2DepartmentLabels[id].en);
    }
    for (const status of v2LifecycleStatuses) {
      expect(v2LifecycleLabels[status].en).toBeTruthy();
      expect(v2LifecycleLabels[status].my).toMatch(/[\u1000-\u109f]/u);
      expect(getV2LifecycleLabel(status, "my")).toBe(v2LifecycleLabels[status].my);
    }
    for (const state of staffEmploymentStates) {
      expect(staffEmploymentLabels[state].en).toBeTruthy();
      expect(staffEmploymentLabels[state].my).toMatch(/[\u1000-\u109f]/u);
    }
    for (const state of staffAvailabilityStates) {
      expect(staffAvailabilityLabels[state].en).toBeTruthy();
      expect(staffAvailabilityLabels[state].my).toMatch(/[\u1000-\u109f]/u);
    }
  });

  it("parses V2 tickets and rejects unknown categories, statuses, and raw keys", () => {
    expect(parseV2TicketContract(v2Ticket)).toEqual(v2Ticket);
    expect(() => parseV2TicketContract({ ...v2Ticket, categoryId: "card_atm" })).toThrow();
    expect(() => parseV2TicketContract({ ...v2Ticket, status: "in_progress" })).toThrow();
    expect(() => parseV2TicketContract({ ...v2Ticket, category_id: "general_complaints" })).toThrow();
    expect(() => parseV2TicketContract({ ...v2Ticket, extra: true })).toThrow();
  });

  it("reads recognizable unversioned V1 tickets as V1 without conversion", () => {
    expect(readTicketVersion({ status: "triaged", departmentId: "card_atm" })).toBe("v1");
    expect(readTicketVersion({ schemaVersion: "v1", workflowVersion: "v1", taxonomyVersion: "v1" })).toBe("v1");
  });

  it("rejects unknown, partial, inconsistent, and unsafe versions", () => {
    expect(() => readTicketVersion({ status: "unknown", departmentId: "card_atm" })).toThrow();
    expect(() => readTicketVersion({ schemaVersion: "v2" })).toThrow();
    expect(() => readTicketVersion({ schemaVersion: "v2", workflowVersion: "v1", taxonomyVersion: "v2" })).toThrow();
    expect(() => readTicketVersion({ schema_version: "v1" })).toThrow();
  });
});

