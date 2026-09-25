import { useState } from "react";

export function Field({ label, children }) {
  return (
    <label className="w-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Button({ children, secondary, ...props }) {
  return (
    <button
      className={secondary ? "w-button secondary" : "w-button"}
      {...props}
    >
      {children}
    </button>
  );
}
export function ErrorBox({ error }) {
  return error ? (
    <div className="w-error" role="alert">
      {error}
    </div>
  ) : null;
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run, setError };
}
