const encoder = new TextEncoder();

function base64Url(bytes) {
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function getCookie(request, name) {
  const value = request.headers.get("Cookie") || "";
  return value.split(";").map(part => part.trim()).find(part => part.startsWith(`${name}=`))?.slice(name.length + 1) || "";
}

async function signature(value, secret) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return base64Url(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value))));
}

export async function createSession(env) {
  const expiry = Math.floor(Date.now() / 1000) + 60 * 60 * 12;
  const value = `v1.${expiry}`;
  return `${value}.${await signature(value, env.SESSION_SECRET)}`;
}

export async function isAuthorized(request, env) {
  if (!env.SESSION_SECRET) return false;
  const token = getCookie(request, "tr_admin");
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== "v1" || !/^\d+$/.test(parts[1])) return false;
  if (Number(parts[1]) < Math.floor(Date.now() / 1000)) return false;
  const value = `${parts[0]}.${parts[1]}`;
  return parts[2] === await signature(value, env.SESSION_SECRET);
}

export function sessionCookie(value) {
  return `tr_admin=${value}; Path=/; Max-Age=43200; HttpOnly; Secure; SameSite=Strict`;
}

export function clearSessionCookie() {
  return "tr_admin=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict";
}
