import { Navigate, Route, Routes } from "react-router-dom";

import { ApiBanner } from "./components/ApiBanner";
import { ComingSoon } from "./components/ComingSoon";
import { Sidebar } from "./components/Sidebar";
import { TransactionPanel } from "./components/TransactionPanel";
import { Accounts } from "./pages/Accounts";
import { Categories } from "./pages/Categories";
import { Dashboard } from "./pages/Dashboard";
import { Transactions } from "./pages/Transactions";
import { PanelProvider } from "./state/panel";
import { PeriodProvider } from "./state/period";

export function App() {
  return (
    <PeriodProvider>
      <PanelProvider>
        <Sidebar />
        <main className="main">
          <ApiBanner />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/categories" element={<Categories />} />
            <Route
              path="/investments"
              element={<ComingSoon title="Investments">Trades, holdings and your returns vs the S&P 500 arrive with feature 5.</ComingSoon>}
            />
            <Route
              path="/recurring"
              element={<ComingSoon title="Recurring">Spotting repeat bills and showing what's coming up arrives with feature 4.</ComingSoon>}
            />
            <Route
              path="/goals"
              element={<ComingSoon title="Goals">Savings goals linked to an account arrive with feature 6.</ComingSoon>}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <TransactionPanel />
      </PanelProvider>
    </PeriodProvider>
  );
}
