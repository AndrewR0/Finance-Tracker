import { Navigate, Route, Routes } from "react-router-dom";

import { ApiBanner } from "./components/ApiBanner";
import { Sidebar } from "./components/Sidebar";
import { TransactionPanel } from "./components/TransactionPanel";
import { Accounts } from "./pages/Accounts";
import { Categories } from "./pages/Categories";
import { Dashboard } from "./pages/Dashboard";
import { Goals } from "./pages/Goals";
import { Import } from "./pages/Import";
import { Investments } from "./pages/Investments";
import { Recurring } from "./pages/Recurring";
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
            <Route path="/import" element={<Import />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/categories" element={<Categories />} />
            <Route path="/investments" element={<Investments />} />
            <Route path="/recurring" element={<Recurring />} />
            <Route path="/goals" element={<Goals />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
        <TransactionPanel />
      </PanelProvider>
    </PeriodProvider>
  );
}
