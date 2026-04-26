import { useEffect, type PropsWithChildren, type ReactNode } from "react";

interface ModalProps {
  title: string;
  subtitle?: string | null;
  isOpen: boolean;
  onClose: () => void;
  /** Дополнительные кнопки слева от «Закрыть» */
  actions?: ReactNode;
}

export function Modal({
  title,
  subtitle,
  isOpen,
  onClose,
  actions,
  children,
}: PropsWithChildren<ModalProps>) {
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
        className="modal"
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
