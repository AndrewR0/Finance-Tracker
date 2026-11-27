import { describe, expect, it } from "vitest";

import { backupLabel } from "./backups";

const NOW = new Date(2026, 10, 26, 20, 0); // Nov 26, 8:00 PM local

describe("backupLabel", () => {
  it("today and yesterday are fine", () => {
    expect(backupLabel("2026-11-26T03:00:01", NOW)).toEqual({ text: "Backed up today, 3:00 AM", stale: false });
    expect(backupLabel("2026-11-25T03:00:01", NOW)).toEqual({ text: "Backed up yesterday, 3:00 AM", stale: false });
  });

  it("older than two days is a warning", () => {
    expect(backupLabel("2026-11-24T21:00:00", NOW)).toEqual({ text: "Last backup Nov 24", stale: false }); // 47 hours
    expect(backupLabel("2026-11-23T03:00:00", NOW)).toEqual({ text: "Last backup Nov 23", stale: true });
  });

  it("no backups at all is a warning", () => {
    expect(backupLabel(null, NOW)).toEqual({ text: "No backups yet", stale: true });
  });
});
