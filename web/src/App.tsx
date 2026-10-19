import { Navigate, Route, Routes } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { useAuth } from "./lib/auth";
import { Layout } from "./components/Layout";
import { PageLoader } from "./components/ui";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import Queue from "./pages/Queue";
import ApplicationPage from "./pages/ApplicationPage";
import ProfilePage from "./pages/ProfilePage";
import SettingsPage from "./pages/SettingsPage";
import LimitsPage from "./pages/LimitsPage";

export default function App() {
  const { me, loading } = useAuth();
  if (loading) return <PageLoader />;
  if (!me) {
    return (
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Layout>
      <AnimatePresence mode="wait">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/application/:id" element={<ApplicationPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/limits" element={<LimitsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AnimatePresence>
    </Layout>
  );
}
