// Shared display-formatting helpers, mirroring the old prototype's
// fmtNum/fmtBool conventions (see git history: pre-React
// gcs/frontend/index.html).

export function fmtNum(n: number | null | undefined, digits = 2): string {
  return typeof n === "number" ? n.toFixed(digits) : "—";
}

export function fmtOrUnavailable(n: number | null | undefined, suffix = "", digits = 2): string {
  return typeof n === "number" ? `${n.toFixed(digits)}${suffix}` : "unavailable";
}
