import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { DashboardPage } from "@/pages/Dashboard";
import { JobsPage } from "@/pages/Jobs";
import { LiteLLMPage } from "@/pages/LiteLLM";
import { ModelsPage } from "@/pages/Models";
import { MonitoringPage } from "@/pages/Monitoring";
import { PresetsPage } from "@/pages/Presets";
import { RuntimePage } from "@/pages/Runtime";
import { SettingsPage } from "@/pages/Settings";

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate replace to="/dashboard" />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/presets" element={<PresetsPage />} />
        <Route path="/runtime" element={<RuntimePage />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/litellm" element={<LiteLLMPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate replace to="/dashboard" />} />
      </Routes>
    </Layout>
  );
}
