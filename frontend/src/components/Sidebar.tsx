import { useEffect, useRef, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { useBackupStatus, useHealth } from "../api/hooks";
import { backupLabel } from "../lib/backups";

const ICONS: Record<string, ReactNode> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>
  ),
  transactions: <path d="M4 6h16M4 12h16M4 18h10" />,
  accounts: (
    <>
      <rect x="3" y="6" width="18" height="13" rx="2" />
      <path d="M3 10h18" />
    </>
  ),
  investments: <path d="M4 18l5-6 4 3 7-9" />,
  retirement: (
    <>
      <path d="M12 3v3M12 18v3M5 12H3M21 12h-2" />
      <circle cx="12" cy="12" r="6" />
      <path d="M12 9v3l2 2" />
    </>
  ),
  recurring: <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4" />,
  goals: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  categories: <path d="M4 7h7l2 2h7v10H4z" />,
  review: (
    <>
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M4 10h16M9 3v4M15 3v4" />
    </>
  ),
  budgets: (
    <>
      <rect x="4" y="5" width="16" height="4" rx="1" />
      <rect x="4" y="11" width="11" height="4" rx="1" />
      <rect x="4" y="17" width="7" height="3" rx="1" />
    </>
  ),
};

const LINKS: { to: string; label: string; icon: string; soon?: boolean }[] = [
  { to: "/", label: "Dashboard", icon: "dashboard" },
  { to: "/transactions", label: "Transactions", icon: "transactions" },
  { to: "/accounts", label: "Accounts", icon: "accounts" },
  { to: "/categories", label: "Categories", icon: "categories" },
  { to: "/budgets", label: "Budgets", icon: "budgets" },
  { to: "/investments", label: "Investments", icon: "investments" },
  { to: "/retirement", label: "Retirement", icon: "retirement" },
  { to: "/recurring", label: "Recurring", icon: "recurring" },
  { to: "/goals", label: "Goals", icon: "goals" },
  { to: "/review", label: "Year in Review", icon: "review" },
];

export function Sidebar() {
  // On a phone the nav is a strip you swipe sideways. Keep the current page's link in view,
  // so opening Goals (say) from a link elsewhere doesn't leave it hidden off the edge.
  const nav = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useEffect(() => {
    const strip = nav.current;
    const link = strip?.querySelector<HTMLElement>("a.on");
    if (!strip || !link || strip.scrollWidth <= strip.clientWidth) return; // desktop: nothing to scroll
    const offset = link.getBoundingClientRect().left - strip.getBoundingClientRect().left;
    strip.scrollTo({ left: strip.scrollLeft + offset - (strip.clientWidth - link.offsetWidth) / 2 });
  }, [pathname]);

  return (
    <aside className="side">
      <div className="brand">
        <i />
        Finance Tracker
        <DemoBadge />
      </div>
      <nav className="nav" ref={nav}>
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.to === "/"} className={({ isActive }) => (isActive ? "on" : "")}>
            <svg viewBox="0 0 24 24">{ICONS[link.icon]}</svg>
            {link.label}
            {link.soon && <span className="soon">soon</span>}
          </NavLink>
        ))}
      </nav>
      <BackupLine />
    </aside>
  );
}

/** "Backed up today, 3:00 AM", or a warning when the nightly backup seems to have stopped. */
function BackupLine() {
  const status = useBackupStatus().data;
  const demo = useHealth().data?.demo;
  if (demo) return <div className="foot">Demo · every number here is made up</div>;
  if (!status) return <div className="foot">Your data stays on your own server</div>;
  const label = backupLabel(status.last_backup_at ?? null, new Date());
  return (
    <div className="foot" title={`${status.count} backups kept`} style={label.stale ? { color: "var(--bad)" } : undefined}>
      {label.stale ? "⚠ " : ""}
      {label.text}
    </div>
  );
}

/** A "DEMO" label on the copy of the app that runs on made-up data (for showing friends). */
function DemoBadge() {
  const demo = useHealth().data?.demo;
  if (!demo) return null;
  return (
    <span className="demo-badge" title="This copy runs on made-up data. None of it is real.">
      DEMO
    </span>
  );
}
