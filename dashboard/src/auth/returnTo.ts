/** Only application-local destinations may survive authentication. */
export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\s]/.test(value)) return "/lakes";
  try {
    const decoded = decodeURIComponent(value);
    if (/[\\\s]/.test(decoded) || decoded.startsWith("//") || decoded.startsWith("/%2f")) return "/lakes";
    const url = new URL(value, "https://lakesafe.invalid");
    const decodedUrl = new URL(decoded, "https://lakesafe.invalid");
    if (url.origin !== "https://lakesafe.invalid" || /^\/(login|signup|verify-2fa|forgot-password|reset-password)(\/|$)/.test(decodedUrl.pathname)) return "/lakes";
    return url.pathname + url.search + url.hash;
  } catch { return "/lakes"; }
}
export function authDestination(path: string, returnTo: string): string {
  const target = safeReturnTo(returnTo);
  return target === "/lakes" ? path : `${path}?returnTo=${encodeURIComponent(target)}`;
}
