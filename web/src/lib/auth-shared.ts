// Rules shared by the proxy, the auth callback and the auth actions. No
// server-only imports: the proxy loads this too.

/** Only same-site paths, so a crafted ?next= cannot bounce a login elsewhere. */
export function safeNext(next: string | null | undefined, fallback = "/app"): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : fallback;
}

/** Pages for signed-out people; a signed-in visitor is sent on to the app. */
export const SIGNED_OUT_ONLY = ["/login", "/signup", "/forgot"];

/** Pages that need a session. Everything else is public. */
export const SIGNED_IN_ONLY = ["/app", "/field", "/onboarding", "/reset-password"];

export function under(path: string, prefixes: string[]): boolean {
  return prefixes.some((p) => path === p || path.startsWith(`${p}/`));
}

export const PASSWORD_MIN = 10;

/** Why a password is unacceptable, or null. Supabase hashes with bcrypt, which reads only 72 bytes. */
export function passwordProblem(password: string | null, email?: string | null): string | null {
  if (!password || password.length < PASSWORD_MIN) return `Use a password of at least ${PASSWORD_MIN} characters.`;
  if (new TextEncoder().encode(password).length > 72) return "Use a password of at most 72 characters.";
  if (email && password.toLowerCase() === email.toLowerCase()) return "Your password cannot be your email address.";
  return null;
}

export function isEmail(s: string | null): s is string {
  return !!s && s.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

/**
 * One-line outcomes shown after a redirect, by code rather than as free text
 * in the URL, so a link cannot make the page say something we never wrote.
 */
export const NOTICES = {
  "signed-out-everywhere": "You are signed out on every device.",
  "account-deleted": "Your account is closed. The organisations you worked in keep their records.",
  "password-reset": "Your new password is set.",
  "email-changed": "Your email address is confirmed.",
  "left-org": "You have left the organisation.",
} as const;

export type NoticeCode = keyof typeof NOTICES;

export function notice(code: string | undefined): string | null {
  return code && Object.hasOwn(NOTICES, code) ? NOTICES[code as NoticeCode] : null;
}
