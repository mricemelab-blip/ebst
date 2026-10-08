/**
 * EBST 邀请码验证 Worker
 * 部署到 Cloudflare Workers，使用 KV 存储
 *
 * ## 部署步骤
 * 1. 注册/登录 Cloudflare (dash.cloudflare.com)
 * 2. 进入 Workers & Pages → Create → Worker
 * 3. 名称：ebst-auth
 * 4. 将 worker.js 内容粘贴到编辑器，保存并部署
 * 5. 创建 KV Namespace：Workers & Pages → KV → Create → 名称：EBST_CODES
 * 6. 回到 Worker → Settings → Variables → KV Namespace Bindings → 添加绑定：
 *    - Variable name: EBST_CODES
 *    - KV namespace: EBST_CODES
 * 7. 记录 Worker 的 URL（如 https://ebst-auth.mricemelab.workers.dev）
 * 8. 更新 index.html 中的 WORKER_URL
 */

// 邀请码从 KV 读取，不再硬编码

// CORS headers
const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default {
  async fetch(request, env) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: CORS_HEADERS });
    }

    try {
      const body = await request.json();
      const { code, phone, name, action } = body;

      // Action: 'verify' = 仅验证邀请码, 'claim' = 绑定手机号
      if (action === 'verify') {
        const codeExists = await env.EBST_CODES.get(`code:${code}`);
        if (codeExists) {
          // 检查是否已被使用
          const existing = await env.EBST_CODES.get(code);
          if (existing) {
            const data = JSON.parse(existing);
            return new Response(JSON.stringify({
              valid: true,
              used: true,
              phone: data.phone,
              name: data.name,
              claimedAt: data.claimedAt
            }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
          } else {
            return new Response(JSON.stringify({
              valid: true,
              used: false
            }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
          }
        } else {
          return new Response(JSON.stringify({
            valid: false
          }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
        }
      }

      if (action === 'claim') {
        if (!code || !phone || !name) {
          return new Response(JSON.stringify({
            success: false,
            error: '缺少必要参数'
          }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
        }

        // 检查是否已被使用
        const existing = await env.EBST_CODES.get(code);
        if (existing) {
          const data = JSON.parse(existing);
          // 如果手机号匹配，允许（同一学员）
          if (data.phone === phone) {
            return new Response(JSON.stringify({
              success: true,
              message: '欢迎回来',
              name: data.name
            }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
          } else {
            return new Response(JSON.stringify({
              success: false,
              error: '该邀请码已被其他学员使用'
            }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
          }
        }

        // 首次使用，绑定
        await env.EBST_CODES.put(code, JSON.stringify({
          phone: phone,
          name: name,
          claimedAt: new Date().toISOString()
        }));

        return new Response(JSON.stringify({
          success: true,
          message: '验证成功'
        }), { headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' } });
      }

      return new Response(JSON.stringify({ error: '未知操作' }), {
        status: 400,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' }
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 500,
        headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' }
      });
    }
  }
};
