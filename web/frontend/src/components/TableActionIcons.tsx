import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Иконка «редактировать карточку» (карандаш). */
export function IconEdit({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
    </svg>
  );
}

/** Иконка «скачать / докачать веса». */
export function IconCloudArrowDown({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  );
}

/** Иконка «экспорт в файл» (.env). */
export function IconArrowUpTray({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-3L12 3m0 0l4.5 10.5M12 3v10.5" />
    </svg>
  );
}

/** Иконка «удалить». */
export function IconTrash({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12.562 0a48.11 48.11 0 0 0 3.478-.397m7.5 0v-.916c0-1.18-.91-2.13-2.09-2.2a48.1 48.1 0 0 0-1.64-.03c-.7 0-1.34.2-1.9.5" />
    </svg>
  );
}

type IconBtnVariant = "ghost" | "primary" | "default" | "danger";

const variantClass: Record<IconBtnVariant, string> = {
  ghost: "btn btn--ghost btn--icon",
  primary: "btn btn--primary btn--icon",
  default: "btn btn--icon",
  danger: "btn btn--danger btn--icon",
};

export function IconActionButton({
  label,
  variant = "ghost",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  variant?: IconBtnVariant;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`${variantClass[variant]} ${className}`.trim()}
      title={label}
      aria-label={label}
      {...rest}
    >
      {children}
    </button>
  );
}
