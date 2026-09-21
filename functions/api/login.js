import { createSession, sessionCookie } from "../_lib/auth.js";

export async function onRequestPost({ request, env }) {
  if (!env.ADMIN_PASSWORD || !env.SESSION_SECRET) return new Response("管理员环境变量尚未配置", { status: 503 });
  const { password } = await request.json().catch(() => ({}));
  if (!password || password !== env.ADMIN_PASSWORD) return new Response("密码错误", { status: 401 });
  return Response.json({ ok: true }, { headers: { "Set-Cookie": sessionCookie(await createSession(env)) } });
}
