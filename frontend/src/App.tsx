import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { EvaluationPage } from "./pages/EvaluationPage";
import { InsightsPage } from "./pages/InsightsPage";
import { HistoryPage } from "./pages/HistoryPage";
import { HowItWorksPage } from "./pages/HowItWorksPage";
import { IntakePage } from "./pages/IntakePage";
import { WorkPage } from "./pages/WorkPage";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/queue" replace />} />
        <Route path="queue/:id?" element={<WorkPage view="queue" />} />
        <Route path="compliance/:id?" element={<WorkPage view="compliance" />} />
        <Route path="sample/:id?" element={<WorkPage view="sample" />} />
        <Route path="all/:id?" element={<WorkPage view="all" />} />
        <Route path="intake" element={<IntakePage />} />
        <Route path="history/:id" element={<HistoryPage />} />
        <Route path="how-it-works" element={<HowItWorksPage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function NotFound() {
  return (
    <div className="page">
      <h1 className="ll-display">Page not found</h1>
      <p className="muted">
        Go to the <a href="/queue">review queue</a>.
      </p>
    </div>
  );
}
