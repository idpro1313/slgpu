/** Сохранение Blob в файл через браузер (без серверного attachment). */

export function saveBlobToClient(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
}

export function saveTextFile(
  filename: string,
  text: string,
  mime = "application/json;charset=utf-8",
): void {
  saveBlobToClient(new Blob([text], { type: mime }), filename);
}
