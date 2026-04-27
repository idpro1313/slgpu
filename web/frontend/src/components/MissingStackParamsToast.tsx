import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  setMissingStackParamsHandler,
  type StackErrorPayload,
} from "@/stackErrorBus";

/**
 * Глобальный баннер при 409 ``missing_stack_params`` (см. ``api/client.ts``).
 */
export function MissingStackParamsToast() {
  const [last, setLast] = useState<StackErrorPayload | null>(null);

  useEffect(() => {
    setMissingStackParamsHandler((p) => setLast(p));
    return () => setMissingStackParamsHandler(null);
  }, []);

  if (!last?.keys?.length) {
    return null;
  }

  const q = encodeURIComponent(last.keys.join(","));
  return (
    <div className="stack-missing-banner" role="alert">
      <div className="stack-missing-banner__text">
        Не заданы параметры стека
        {last.scope ? ` (${last.scope})` : ""}:{" "}
        <span className="mono">{last.keys.join(", ")}</span>
      </div>
      <Link className="btn btn--sm" to={`/settings?missing=${q}`}>
        Перейти в Настройки
      </Link>
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        onClick={() => setLast(null)}
      >
        Закрыть
      </button>
    </div>
  );
}
