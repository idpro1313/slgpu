import type { PropsWithChildren, ReactNode } from "react";

interface SectionProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function Section({ title, subtitle, actions, children }: PropsWithChildren<SectionProps>) {
  return (
    <section className="section">
      <header className="section__head">
        <div>
          <h2 className="section__title">{title}</h2>
          {subtitle ? <p className="section__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex flex--gap-sm flex--wrap">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}
