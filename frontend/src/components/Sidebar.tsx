import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

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
  recurring: <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4h-4" />,
  goals: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  categories: <path d="M4 7h7l2 2h7v10H4z" />,
};

const LINKS: { to: string; label: string; icon: string; soon?: boolean }[] = [
  { to: "/", label: "Dashboard", icon: "dashboard" },
  { to: "/transactions", label: "Transactions", icon: "transactions" },
  { to: "/accounts", label: "Accounts", icon: "accounts" },
  { to: "/categories", label: "Categories", icon: "categories" },
  { to: "/investments", label: "Investments", icon: "investments", soon: true },
  { to: "/recurring", label: "Recurring", icon: "recurring", soon: true },
  { to: "/goals", label: "Goals", icon: "goals", soon: true },
];

export function Sidebar() {
  return (
    <aside className="side">
      <div className="brand">
        <i />
        Finance Tracker
      </div>
      <nav className="nav">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.to === "/"} className={({ isActive }) => (isActive ? "on" : "")}>
            <svg viewBox="0 0 24 24">{ICONS[link.icon]}</svg>
            {link.label}
            {link.soon && <span className="soon">soon</span>}
          </NavLink>
        ))}
      </nav>
      <div className="foot">Local only · your data stays on this PC</div>
    </aside>
  );
}
