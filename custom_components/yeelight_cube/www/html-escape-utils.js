/**
 * Shared HTML-escaping helper for cards that build DOM via innerHTML string
 * templates (palette card, list/gallery utils, ...).
 *
 * User-controlled strings (palette names, pixel-art names — settable via
 * rename services and JSON import) MUST be escaped before being interpolated
 * into an HTML string, otherwise a name like `<img src=x onerror=...>`
 * becomes stored XSS executing for every dashboard viewer.
 *
 * Lit `html\`...\`` templates escape automatically and do NOT need this.
 */
export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
