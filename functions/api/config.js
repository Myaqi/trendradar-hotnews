import { isAuthorized } from "../_lib/auth.js";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function base64Encode(text) {
  let binary = "";
  for (const byte of encoder.encode(text)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64Decode(text) {
  const binary = atob(text.replaceAll("\n", ""));
  return decoder.decode(Uint8Array.from(binary, char => char.charCodeAt(0)));
}

function githubHeaders(token) {
  return { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "TrendRadar-Admin" };
}

function settings(env) {
  return { owner: env.GITHUB_OWNER || "Myaqi", repo: env.GITHUB_REPO || "trendradar-hotnews", branch: env.GITHUB_BRANCH || "master" };
}

async function getFile(env) {
  if (!env.GITHUB_TOKEN) throw new Error("未配置 GITHUB_TOKEN");
  const { owner, repo, branch } = settings(env);
  const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/config/config.yaml?ref=${encodeURIComponent(branch)}`, { headers: githubHeaders(env.GITHUB_TOKEN) });
  if (!response.ok) throw new Error(`读取云端配置失败（${response.status}）`);
  const data = await response.json();
  return { content: base64Decode(data.content), sha: data.sha, ...settings(env) };
}

function unauthorized() { return new Response("请先登录管理台", { status: 401 }); }

export async function onRequestGet({ request, env }) {
  if (!await isAuthorized(request, env)) return unauthorized();
  try { return Response.json({ ok: true, ...(await getFile(env)) }); }
  catch (error) { return new Response(error.message, { status: 502 }); }
}

export async function onRequestPut({ request, env }) {
  if (!await isAuthorized(request, env)) return unauthorized();
  const { content } = await request.json().catch(() => ({}));
  if (typeof content !== "string" || content.length < 50 || content.length > 600000 || content.includes("\0")) return new Response("配置内容无效", { status: 400 });
  try {
    const file = await getFile(env);
    const api = `https://api.github.com/repos/${file.owner}/${file.repo}`;
    const update = await fetch(`${api}/contents/config/config.yaml`, {
      method: "PUT", headers: { ...githubHeaders(env.GITHUB_TOKEN), "Content-Type": "application/json" },
      body: JSON.stringify({ message: "chore: update TrendRadar configuration from admin", content: base64Encode(content), sha: file.sha, branch: file.branch })
    });
    if (!update.ok) throw new Error(`保存配置失败（${update.status}）`);
    const dispatch = await fetch(`${api}/actions/workflows/crawler.yml/dispatches`, {
      method: "POST", headers: { ...githubHeaders(env.GITHUB_TOKEN), "Content-Type": "application/json" }, body: JSON.stringify({ ref: file.branch })
    });
    if (!dispatch.ok) throw new Error(`配置已保存，但启动刷新失败（${dispatch.status}）`);
    return Response.json({ ok: true, message: "已保存，并启动网页刷新任务。" });
  } catch (error) { return new Response(error.message, { status: 502 }); }
}
