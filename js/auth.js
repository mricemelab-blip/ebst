/**
 * EBST Auth Helper — 前端认证逻辑
 * 被 index.html / dashboard.html / ch*.html 共同引用
 *
 * Worker URL 通过 WORKER_URL 常量配置
 * 部署后替换为实际的 workers.dev 域名
 */

// ─── 配置 ──────────────────────────────────────────────
const WORKER_URL = 'https://ebst-auth.mrice-melab.workers.dev';
const TOKEN_KEY = 'ebst_token';
const STUDENT_KEY = 'ebst_student';
const FP_KEY = 'ebst_device_fp';
const FETCH_TIMEOUT = 8000;

function fetchWithTimeout(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

// ─── Token 管理 ────────────────────────────────────────
function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(STUDENT_KEY);
}

function getStudentInfo() {
  try {
    return JSON.parse(localStorage.getItem(STUDENT_KEY) || 'null');
  } catch {
    return null;
  }
}

function setStudentInfo(info) {
  localStorage.setItem(STUDENT_KEY, JSON.stringify(info));
}

// ─── 设备指纹 ──────────────────────────────────────────
async function getDeviceFingerprint() {
  // 缓存指纹（同一会话内不重复计算）
  let fp = sessionStorage.getItem(FP_KEY);
  if (fp) return fp;

  if (window.EBSTFingerprint) {
    fp = await window.EBSTFingerprint.generate();
  } else {
    // 降级方案：简单指纹
    const raw = [
      navigator.userAgent,
      screen.width + 'x' + screen.height,
      navigator.language,
      new Date().getTimezoneOffset(),
    ].join('|');
    fp = btoa(raw).replace(/=/g, '').substring(0, 32);
  }

  sessionStorage.setItem(FP_KEY, fp);
  return fp;
}

// ─── API 调用 ──────────────────────────────────────────
async function apiCheckCode(code, turnstileToken) {
  const body = { code };
  if (turnstileToken) body.turnstileToken = turnstileToken;
  const res = await fetchWithTimeout(`${WORKER_URL}/api/check-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiLogin(phone, name, invitationCode, turnstileToken) {
  const fp = await getDeviceFingerprint();
  const body = { phone, name, invitationCode, deviceFingerprint: fp };
  if (turnstileToken) body.turnstileToken = turnstileToken;
  const res = await fetchWithTimeout(`${WORKER_URL}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiVerify() {
  const token = getToken();
  if (!token) return { valid: false, reason: '未登录' };

  const fp = await getDeviceFingerprint();
  const res = await fetchWithTimeout(`${WORKER_URL}/api/verify`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-Device-Fingerprint': fp,
    },
  });
  return res.json();
}

async function apiLogout() {
  const token = getToken();
  if (!token) return;

  const fp = await getDeviceFingerprint();
  await fetchWithTimeout(`${WORKER_URL}/api/logout`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-Device-Fingerprint': fp,
    },
  });
}

// ─── 页面鉴权（供 dashboard / chapter 页面使用）────────
async function requireAuth() {
  const token = getToken();
  if (!token) {
    window.location.href = 'index.html';
    return null;
  }

  try {
    const result = await apiVerify();
    if (!result.valid) {
      clearToken();
      window.location.href = 'index.html';
      return null;
    }
    return result;
  } catch (e) {
    // Worker 不可达 → 降级：允许访问（避免断网无法学习）
    console.warn('[EBST Auth] Worker unreachable, fallback to local check');
    const student = getStudentInfo();
    if (!student || !student.name) {
      window.location.href = 'index.html';
      return null;
    }
    return { valid: true, name: student.name, degraded: true };
  }
}

// ─── 登出操作 ──────────────────────────────────────────
async function logout() {
  try {
    await apiLogout();
  } catch (e) {
    // 忽略网络错误
  }
  clearToken();
  window.location.href = 'index.html';
}

// 暴露给全局
window.EBSTAuth = {
  getToken, setToken, clearToken,
  getStudentInfo, setStudentInfo,
  getDeviceFingerprint,
  apiCheckCode, apiLogin, apiVerify, apiLogout,
  requireAuth, logout,
  WORKER_URL,
};
