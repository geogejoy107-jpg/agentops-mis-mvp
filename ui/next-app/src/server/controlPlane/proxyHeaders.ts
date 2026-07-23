const HUMAN_SESSION_COOKIE = "agentops_human_session";

export function stripHumanSessionCookie(rawCookie: string) {
  return rawCookie
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => item.split("=", 1)[0].trim() !== HUMAN_SESSION_COOKIE)
    .join("; ");
}

export function removeHumanSessionCookie(headers: Headers) {
  const rawCookie = headers.get("cookie");
  if (rawCookie === null) return headers;
  const filtered = stripHumanSessionCookie(rawCookie);
  if (filtered) headers.set("cookie", filtered);
  else headers.delete("cookie");
  return headers;
}

function setCookieName(value: string) {
  return value.split(";", 1)[0].split("=", 1)[0].trim();
}

export function removeHumanSessionSetCookie(headers: Headers) {
  const compatible = headers as Headers & { getSetCookie?: () => string[] };
  const values = compatible.getSetCookie?.() || [];
  if (values.length) {
    headers.delete("set-cookie");
    for (const value of values) {
      if (setCookieName(value) !== HUMAN_SESSION_COOKIE) headers.append("set-cookie", value);
    }
    return headers;
  }
  const combined = headers.get("set-cookie");
  if (combined && combined.includes(`${HUMAN_SESSION_COOKIE}=`)) {
    headers.delete("set-cookie");
  }
  return headers;
}
