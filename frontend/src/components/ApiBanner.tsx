import { useHealth } from "../api/hooks";

/** A visible warning when the backend isn't running, instead of a page of empty cards. */
export function ApiBanner() {
  const { isError } = useHealth();
  if (!isError) return null;
  return (
    <div className="banner">
      Can't reach the API. Start the backend from <code>backend\</code> with{" "}
      <code>uv run uvicorn app.main:app --reload</code>, and this page will catch up on its own.
    </div>
  );
}
