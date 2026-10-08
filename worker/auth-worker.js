/**
 * EBST Auth Worker — Cloudflare Worker + KV
 *
 * 功能:
 *   POST /api/login    登录（邀请码 + 手机号 + 设备指纹）
 *   GET  /api/verify   验证 token
 *   POST /api/logout   登出（移除当前设备指纹）
 *   GET  /api/chapter/:id  代理章节 HTML（需 token）
 *   POST /api/upload-chapter  上传章节到 KV（管理员）
 *
 * KV namespace: EBST_AUTH
 * KV key 结构:
 *   user:{phone}   → 用户记录 JSON
 *   token:{token}  → phone（反向索引，快速验证 token）
 *   chapter:{id}   → 章节 HTML 原文
 *
 * 部署: wrangler deploy
 */

// ─── 配置 ─────────────────────────────────────────────
// 邀请码存在 KV 中，key 格式: code:{code}，value: "1"
const TOKEN_TTL = 604800;          // 7 天（秒）
const MAX_DEVICES = 2;             // 每个手机号最多绑定设备数
const ADMIN_SECRET = 'ebst2026auth';  // 管理员密钥

// ── Rate Limiting & Turnstile ─────────────────────────
const RATE_LIMIT_WINDOW = 600;     // 10 分钟窗口（秒）
const RATE_LIMIT_MAX = 5;          // 窗口内最多尝试次数
const TURNSTILE_THRESHOLD = 3;     // 连续失败 3 次后要求 Turnstile

// ─── CORS ──────────────────────────────────────────────
function corsHeaders(origin) {
  const allowed = [
    'https://mricemelab-blip.github.io',
    'http://localhost',
    'https://ebst.3hfit.com'                    // ← 如有自定义域名
  ];
  const allowOrigin = allowed.some(a => origin && origin.startsWith(a))
    ? origin
    : allowed[0];
  return {
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}

function json(data, status = 200, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders(origin) },
  });
}

// ─── 工具函数 ──────────────────────────────────────────
async function sha256(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function generateToken(phone) {
  const ts = Date.now().toString(36);
  const rand = crypto.randomUUID();
  return sha256(`${phone}:${ts}:${rand}`).then(hash => hash.substring(0, 48));
}

function getToken(request) {
  const auth = request.headers.get('Authorization') || '';
  if (auth.startsWith('Bearer ')) return auth.slice(7);
  return null;
}

function getIP(request) {
  return request.headers.get('CF-Connecting-IP') || 'unknown';
}

// ─── 主入口 ────────────────────────────────────────────
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders(origin) });
    }

    // 路由
    const path = url.pathname;

    if (path === '/api/login' && request.method === 'POST') {
      return handleLogin(request, env, origin);
    }
    if (path === '/api/verify' && request.method === 'GET') {
      return handleVerify(request, env, origin);
    }
    if (path === '/api/logout' && request.method === 'POST') {
      return handleLogout(request, env, origin);
    }
    if (path.startsWith('/api/chapter/') && request.method === 'GET') {
      return handleChapter(request, env, origin);
    }
    if (path === '/api/upload-chapter' && request.method === 'POST') {
      return handleUploadChapter(request, env, origin);
    }
    if (path === '/api/check-code' && request.method === 'POST') {
      return handleCheckCode(request, env, origin);
    }

    return json({ error: 'Not found' }, 404, origin);
  },
};

// ─── POST /api/login ───────────────────────────────────
async function handleLogin(request, env, origin) {
  try {
    const body = await request.json();
    const { phone, name, invitationCode, deviceFingerprint, turnstileToken } = body;

    // 参数校验
    if (!phone || !name || !invitationCode || !deviceFingerprint) {
      return json({ success: false, error: '缺少必要参数' }, 400, origin);
    }

    const ip = getIP(request);

    // 频率限制 + Turnstile 检查
    const rateKey = `ratelimit:${ip}`;
    const rateRaw = await env.EBST_AUTH.get(rateKey);
    let rateData = rateRaw ? JSON.parse(rateRaw) : { fails: 0, windowStart: Date.now() };

    if (Date.now() - rateData.windowStart > RATE_LIMIT_WINDOW * 1000) {
      rateData = { fails: 0, windowStart: Date.now() };
    }

    if (rateData.fails >= RATE_LIMIT_MAX) {
      return json({
        success: false,
        error: '尝试次数过多，请完成人机验证后重试',
        requireTurnstile: true,
      }, 429, origin);
    }

    if (rateData.fails >= TURNSTILE_THRESHOLD) {
      if (!turnstileToken) {
        return json({
          success: false,
          error: '请完成人机验证',
          requireTurnstile: true,
        }, 403, origin);
      }
      const tsSecret = env.TURNSTILE_SECRET_KEY;
      if (tsSecret) {
        const tsRes = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ secret: tsSecret, response: turnstileToken, remoteip: ip }),
        });
        const tsData = await tsRes.json();
        if (!tsData.success) {
          return json({ success: false, error: '人机验证失败' }, 403, origin);
        }
      }
    }

    // 验证邀请码（从 KV 读取）
    const codeValid = await env.EBST_AUTH.get(`code:${invitationCode}`);
    if (!codeValid) {
      rateData.fails++;
      await env.EBST_AUTH.put(rateKey, JSON.stringify(rateData), {
        expirationTtl: RATE_LIMIT_WINDOW,
      });
      return json({ success: false, error: '邀请码无效' }, 401, origin);
    }

    // 验证成功 → 重置计数器
    await env.EBST_AUTH.delete(rateKey);
    const now = Date.now();

    // 查询已有用户记录
    const userKey = `user:${phone}`;
    const existing = await env.EBST_AUTH.get(userKey);
    let userRecord = existing ? JSON.parse(existing) : null;

    if (userRecord) {
      // 已有用户 → 检查设备指纹
      const deviceIdx = userRecord.devices.findIndex(
        d => d.fingerprint === deviceFingerprint
      );

      if (deviceIdx >= 0) {
        // 设备已注册 → 更新 lastSeen
        userRecord.devices[deviceIdx].lastSeen = now;
        userRecord.devices[deviceIdx].ip = ip;
      } else {
        // 新设备 → 检查设备数限制
        // 清理过期设备（超过 30 天未活跃）
        const thirtyDays = 30 * 24 * 60 * 60 * 1000;
        userRecord.devices = userRecord.devices.filter(
          d => (now - d.lastSeen) < thirtyDays
        );

        if (userRecord.devices.length >= MAX_DEVICES) {
          return json({
            success: false,
            error: '已在其他设备登录，最多支持 2 台设备。请先在旧设备上退出登录。',
            code: 'DEVICE_LIMIT',
          }, 403, origin);
        }

        // 添加新设备
        userRecord.devices.push({
          fingerprint: deviceFingerprint,
          lastSeen: now,
          ip,
          addedAt: now,
        });
      }

      // 更新用户信息
      userRecord.name = name;
      userRecord.lastLogin = now;
      userRecord.invitationCode = invitationCode;
    } else {
      // 新用户
      userRecord = {
        phone,
        name,
        invitationCode,
        devices: [{
          fingerprint: deviceFingerprint,
          lastSeen: now,
          ip,
          addedAt: now,
        }],
        createdAt: now,
        lastLogin: now,
      };
    }

    // 生成 token
    const token = await generateToken(phone);
    const expiresAt = now + TOKEN_TTL * 1000;

    userRecord.token = token;
    userRecord.tokenExpiresAt = expiresAt;

    // 写入 KV
    await env.EBST_AUTH.put(userKey, JSON.stringify(userRecord));
    await env.EBST_AUTH.put(`token:${token}`, phone, {
      expirationTtl: TOKEN_TTL,
    });

    return json({
      success: true,
      token,
      name,
      expiresAt,
    }, 200, origin);

  } catch (e) {
    return json({ success: false, error: e.message }, 500, origin);
  }
}

// ─── GET /api/verify ───────────────────────────────────
async function handleVerify(request, env, origin) {
  try {
    const token = getToken(request);
    if (!token) {
      return json({ valid: false, reason: '未提供 token' }, 401, origin);
    }

    // 通过 token 反向索引查 phone
    const phone = await env.EBST_AUTH.get(`token:${token}`);
    if (!phone) {
      return json({ valid: false, reason: 'token 无效或已过期' }, 401, origin);
    }

    // 查用户记录
    const userRaw = await env.EBST_AUTH.get(`user:${phone}`);
    if (!userRaw) {
      return json({ valid: false, reason: '用户记录不存在' }, 401, origin);
    }

    const user = JSON.parse(userRaw);

    // 检查 token 是否匹配
    if (user.token !== token) {
      return json({ valid: false, reason: 'token 已被替换（在其他设备登录）' }, 401, origin);
    }

    // 检查过期
    if (Date.now() > user.tokenExpiresAt) {
      return json({ valid: false, reason: 'token 已过期，请重新登录' }, 401, origin);
    }

    // 更新 lastSeen（异步，不阻塞响应）
    const deviceFP = request.headers.get('X-Device-Fingerprint');
    if (deviceFP) {
      const device = user.devices.find(d => d.fingerprint === deviceFP);
      if (device) {
        device.lastSeen = Date.now();
        device.ip = getIP(request);
        await env.EBST_AUTH.put(`user:${phone}`, JSON.stringify(user));
      }
    }

    return json({
      valid: true,
      name: user.name,
      phone: user.phone,
    }, 200, origin);

  } catch (e) {
    return json({ valid: false, reason: e.message }, 500, origin);
  }
}

// ─── POST /api/logout ──────────────────────────────────
async function handleLogout(request, env, origin) {
  try {
    const token = getToken(request);
    if (!token) {
      return json({ success: false, error: '未提供 token' }, 401, origin);
    }

    const phone = await env.EBST_AUTH.get(`token:${token}`);
    if (!phone) {
      return json({ success: true }, 200, origin); // 已失效，幂等
    }

    const userRaw = await env.EBST_AUTH.get(`user:${phone}`);
    if (userRaw) {
      const user = JSON.parse(userRaw);

      // 移除当前设备指纹
      const deviceFP = request.headers.get('X-Device-Fingerprint');
      if (deviceFP) {
        user.devices = user.devices.filter(d => d.fingerprint !== deviceFP);
      }

      // 清除 token
      user.token = null;
      user.tokenExpiresAt = 0;
      user.lastLogout = Date.now();

      await env.EBST_AUTH.put(`user:${phone}`, JSON.stringify(user));
    }

    // 删除 token 反向索引
    await env.EBST_AUTH.delete(`token:${token}`);

    return json({ success: true }, 200, origin);

  } catch (e) {
    return json({ success: false, error: e.message }, 500, origin);
  }
}

// ─── GET /api/chapter/:id ──────────────────────────────
async function handleChapter(request, env, origin) {
  try {
    const token = getToken(request);
    if (!token) {
      return json({ valid: false, reason: '未提供 token' }, 401, origin);
    }

    // 验证 token
    const phone = await env.EBST_AUTH.get(`token:${token}`);
    if (!phone) {
      return json({ valid: false, reason: 'token 无效或已过期' }, 401, origin);
    }

    const userRaw = await env.EBST_AUTH.get(`user:${phone}`);
    if (!userRaw) {
      return json({ valid: false, reason: '用户记录不存在' }, 401, origin);
    }

    const user = JSON.parse(userRaw);
    if (user.token !== token || Date.now() > user.tokenExpiresAt) {
      return json({ valid: false, reason: 'token 已失效' }, 401, origin);
    }

    // 提取章节 ID
    const chapterId = request.url.split('/api/chapter/')[1];
    if (!chapterId) {
      return json({ error: '章节 ID 缺失' }, 400, origin);
    }

    // 从 KV 读取章节 HTML
    const chapterKey = `chapter:${chapterId}`;
    const html = await env.EBST_AUTH.get(chapterKey);
    if (!html) {
      return json({ error: '章节内容不存在，请联系管理员上传' }, 404, origin);
    }

    return new Response(html, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        ...corsHeaders(origin),
      },
    });

  } catch (e) {
    return json({ error: e.message }, 500, origin);
  }
}

// ─── POST /api/check-code（前端实时校验邀请码 + 频率限制 + Turnstile）──
async function handleCheckCode(request, env, origin) {
  try {
    const body = await request.json();
    const { code, turnstileToken } = body;
    const ip = getIP(request);
    const rateKey = `ratelimit:${ip}`;

    // 1. 频率限制检查
    const rateRaw = await env.EBST_AUTH.get(rateKey);
    let rateData = rateRaw ? JSON.parse(rateRaw) : { fails: 0, windowStart: Date.now() };

    // 窗口过期则重置
    if (Date.now() - rateData.windowStart > RATE_LIMIT_WINDOW * 1000) {
      rateData = { fails: 0, windowStart: Date.now() };
    }

    // 超过最大尝试次数 → 强制要求 Turnstile
    if (rateData.fails >= RATE_LIMIT_MAX) {
      return json({
        valid: false,
        requireTurnstile: true,
        message: '尝试次数过多，请完成人机验证',
      }, 429, origin);
    }

    // 2. 如果之前失败次数已达阈值，必须提供 Turnstile token
    if (rateData.fails >= TURNSTILE_THRESHOLD) {
      if (!turnstileToken) {
        return json({
          valid: false,
          requireTurnstile: true,
        }, 200, origin);
      }
      // 验证 Turnstile token
      const tsSecret = env.TURNSTILE_SECRET_KEY;
      if (!tsSecret) {
        // 未配置 Turnstile，放行（降级）
        console.warn('[EBST] Turnstile secret not configured, bypassing');
      } else {
        const tsRes = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ secret: tsSecret, response: turnstileToken, remoteip: ip }),
        });
        const tsData = await tsRes.json();
        if (!tsData.success) {
          rateData.fails++;
          await env.EBST_AUTH.put(rateKey, JSON.stringify(rateData), {
            expirationTtl: RATE_LIMIT_WINDOW,
          });
          return json({ valid: false, error: '人机验证失败' }, 403, origin);
        }
      }
    }

    // 3. 验证邀请码
    const trimmedCode = (code || '').trim();
    if (!trimmedCode) {
      return json({ valid: false }, 400, origin);
    }
    const exists = await env.EBST_AUTH.get(`code:${trimmedCode}`);

    if (exists) {
      // 成功 → 重置计数器
      await env.EBST_AUTH.delete(rateKey);
      return json({ valid: true }, 200, origin);
    } else {
      // 失败 → 递增计数
      rateData.fails++;
      await env.EBST_AUTH.put(rateKey, JSON.stringify(rateData), {
        expirationTtl: RATE_LIMIT_WINDOW,
      });

      const needTurnstile = rateData.fails >= TURNSTILE_THRESHOLD;
      return json({
        valid: false,
        requireTurnstile: needTurnstile,
        attemptsLeft: RATE_LIMIT_MAX - rateData.fails,
      }, 200, origin);
    }
  } catch (e) {
    return json({ valid: false, error: e.message }, 500, origin);
  }
}

// ─── POST /api/upload-chapter（管理员接口）────────────────
async function handleUploadChapter(request, env, origin) {
  try {
    const adminKey = request.headers.get('X-Admin-Secret');
    if (adminKey !== ADMIN_SECRET) {
      return json({ error: '未授权' }, 403, origin);
    }

    const { chapterId, html } = await request.json();
    if (!chapterId || !html) {
      return json({ error: '缺少 chapterId 或 html' }, 400, origin);
    }

    await env.EBST_AUTH.put(`chapter:${chapterId}`, html);

    return json({ success: true, chapterId }, 200, origin);

  } catch (e) {
    return json({ error: e.message }, 500, origin);
  }
}
