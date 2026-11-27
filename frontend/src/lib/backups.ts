// The "last backup" line in the sidebar.

/** A backup older than this is a warning: the nightly job runs every day, so two missed nights means it's broken. */
export const STALE_HOURS = 48;

export type BackupLabel = { text: string; stale: boolean };

/**
 * lastBackup: local time of the newest backup, "2026-11-26T03:00:01" (or null).
 * -> "Backed up today, 3:00 AM", "Backed up yesterday, 3:00 AM", "Last backup Nov 20" (stale), ...
 */
export function backupLabel(lastBackup: string | null, now: Date): BackupLabel {
  if (lastBackup === null) return { text: "No backups yet", stale: true };
  const when = new Date(lastBackup);
  const hours = (now.getTime() - when.getTime()) / 3_600_000;
  const time = when.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;
  if (when.getTime() >= startOfToday) return { text: `Backed up today, ${time}`, stale: false };
  if (when.getTime() >= startOfToday - day) return { text: `Backed up yesterday, ${time}`, stale: false };
  const date = when.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return { text: `Last backup ${date}`, stale: hours > STALE_HOURS };
}
