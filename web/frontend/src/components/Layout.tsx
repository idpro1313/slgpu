import type { PropsWithChildren } from "react";
import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/models", label: "Модели" },
  { to: "/presets", label: "Пресеты" },
  { to: "/runtime", label: "Inference" },
  { to: "/monitoring", label: "Мониторинг" },
  { to: "/litellm", label: "LiteLLM" },
  { to: "/jobs", label: "Задачи" },
  { to: "/settings", label: "Настройки" },
];

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__brand">
          <div className="app-header__brand-mark" aria-hidden="true">
            D<span>LLM</span>
          </div>
          <div>
            <div>Develonica.LLM</div>
            <div style={{ fontSize: 12, fontWeight: 400, color: "rgba(245,247,251,0.6)" }}>
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
    </div>
  );
}
