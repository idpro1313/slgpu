import {
  useEffect,
  useRef,
  type PropsWithChildren,
  type ReactNode,
} from "react";

interface ModalProps {
  title: string;
  subtitle?: string | null;
  isOpen: boolean;
  onClose: () => void;
  /** Дополнительные кнопки слева от «Закрыть» */
  actions?: ReactNode;
  /** У широких форм (таблицы, дашборды) */
  size?: "default" | "wide";
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({
  title,
  subtitle,
  isOpen,
  onClose,
  actions,
  size = "default",
  children,
}: PropsWithChildren<ModalProps>) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen || !panelRef.current) return;
    const root = panelRef.current;
    const nodes = [...root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)];
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    first.focus();

    const onTab = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || nodes.length === 0) return;
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    root.addEventListener("keydown", onTab);
    return () => root.removeEventListener("keydown", onTab);
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={size === "wide" ? "modal modal--wide" : "modal"}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        aria-describedby={subtitle ? "modal-subtitle" : undefined}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="modal__head">
          <div className="modal__head-text">
            <h2 id="modal-title" className="modal__title">
              {title}
            </h2>
            {subtitle ? (
              <p id="modal-subtitle" className="modal__subtitle">
                {subtitle}
              </p>
            ) : null}
          </div>
          <div className="modal__toolbar">
            {actions}
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Закрыть
            </button>
          </div>
        </header>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  );
}
