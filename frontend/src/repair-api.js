export const API = import.meta.env.VITE_API_URL || "/api";
let workshop = Number(localStorage.getItem("workshop") || 0);
export function setWorkshop(id) {
  workshop = Number(id);
  localStorage.setItem("workshop", String(id));
}
export function getWorkshop() {
  return workshop;
}
export async function call(
  path,
  { method = "GET", body, raw = false, signal } = {},
) {
  const form = body instanceof FormData;
  const response = await fetch(API + path, {
    method,
    credentials: "include",
    signal,
    headers: {
      ...(workshop ? { "X-Workshop-Id": String(workshop) } : {}),
      ...(!form && body !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("who-could:session-cleared"));
    let data;
    try {
      data = await response.json();
    } catch {
      /* non-JSON gateway response */
    }
    const message = Array.isArray(data?.detail)
      ? data.detail
          .map((x) => `${x.loc?.slice(1).join(".")}: ${x.msg}`)
          .join("; ")
      : data?.detail;
    throw new Error(message || `Ошибка ${response.status}`);
  }
  if (raw) return response.blob();
  return response.status === 204 ? null : response.json();
}
export async function download(path, filename) {
  const blob = await call(path, { raw: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
export async function printDocument(path) {
  const blob = await call(path, { raw: true });
  const frame = document.createElement("iframe");
  frame.style.cssText = "position:fixed;width:1px;height:1px;opacity:0";
  frame.srcdoc = await blob.text();
  document.body.appendChild(frame);
  frame.onload = () => {
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => frame.remove(), 60000);
  };
}
