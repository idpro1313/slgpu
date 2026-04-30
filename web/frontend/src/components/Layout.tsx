import type { PropsWithChildren } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { api } from "@/api/client";
import { MissingStackParamsToast } from "@/components/MissingStackParamsToast";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/models", label: "Модели" },
  { to: "/presets", label: "Пресеты" },
  { to: "/runtime", label: "Inference" },
  { to: "/monitoring", label: "Мониторинг" },
  { to: "/litellm", label: "LiteLLM" },
  { to: "/jobs", label: "Задачи" },
  { to: "/app-logs", label: "Логи" },
  { to: "/log-reports", label: "Отчёты логов" },
  { to: "/docker-logs", label: "Docker" },
  { to: "/benchmarks", label: "Бенчмарки" },
  { to: "/settings", label: "Настройки" },
];

export function Layout({ children }: PropsWithChildren) {
  const health = useQuery({
    queryKey: ["healthz"],
    queryFn: ({ signal }) => api.healthz({ signal }),
    staleTime: 60_000,
  });

  return (
    <div className="app-shell">
      <MissingStackParamsToast />
      <header className="app-header">
        <div className="app-header__brand">
          <div className="app-header__brand-mark" aria-hidden="true" />
          <div>
            <div className="app-header__brand-name">Develonica.LLM</div>
            <div className="app-header__brand-subtitle">
              управление инференсом, мониторингом и LiteLLM
            </div>
          </div>
        </div>
        <nav className="app-header__nav" aria-label="Основная навигация">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <span>Develonica.LLM v{health.data?.version ?? "..."}</span>
        <span>© {new Date().getFullYear()} Igor Yatsishen, Develonica</span>
      </footer>
    </div>
  );
}
