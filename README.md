# EBST Auth System — Cloudflare Worker + KV

## 架构概览

```
GitHub Pages (静态 HTML)     Cloudflare Worker
┌─────────────────────┐     ┌─────────────────────┐
│  index.html         │────→│  POST /api/login     │
│  dashboard.html     │────→│  GET  /api/verify    │
│  ch1-ch17.html      │────→│  POST /api/logout    │
│  js/fingerprint.js  │     │  GET  /api/chapter/:id│
│  js/auth.js         │     │  POST /api/upload-ch  │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                              ┌────────▼────────┐
                              │  KV: EBST_AUTH   │
                              │  user:{phone}    │
                              │  token:{token}   │
                              │  chapter:{id}    │
                              └─────────────────┘
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `worker/auth-worker.js` | Worker 主脚本，处理所有 API |
| `js/fingerprint.js` | 浏览器设备指纹采集（纯 JS，无外部依赖） |
| `js/auth.js` | 前端认证逻辑（登录/验证/登出） |
| `wrangler.toml` | Worker 部署配置 |
| `index.html` | 登录页（已集成 Worker 调用） |
| `dashboard.html` | 仪表盘（已集成 token 验证） |
| `ch*.html` | 章节页面（已集成 token 验证 + 退出按钮） |

## 部署步骤

### 前置条件

- 安装 [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/install-and-update/)
- 登录 Cloudflare 账户：`wrangler login`

### 1. 创建 KV Namespace

```bash
cd sbst/
wrangler kv:namespace create EBST_AUTH
```

输出示例：
```
{ binding = "EBST_AUTH", id = "abc123def456..." }
```

将返回的 `id` 值复制到 `wrangler.toml` 中替换 `PLACEHOLDER_KV_NAMESPACE_ID`。

### 2. 配置 Worker URL

编辑 `js/auth.js`，将 `WORKER_URL` 替换为实际部署后的 Worker 域名：

```javascript
const WORKER_URL = 'https://ebst-auth.your-subdomain.workers.dev';
```

编辑 `worker/auth-worker.js`，在 `corsHeaders()` 函数中更新允许的 origin：

```javascript
const allowed = [
  'https://your-github-username.github.io',  // GitHub Pages 域名
  'https://ebst.3hfit.com'                    // 自定义域名（如有）
];
```

### 3. 部署 Worker

```bash
wrangler deploy
```

部署成功后会显示 Worker URL（如 `https://ebst-auth.xxx.workers.dev`）。

### 4. 上传章节内容到 KV（可选）

如果需要 Worker 代理章节内容（而非直接访问 GitHub Pages 静态文件）：

```bash
# 使用 curl 上传单个章节
curl -X POST https://ebst-auth.xxx.workers.dev/api/upload-chapter \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: CHANGE_ME_TO_A_RANDOM_STRING" \
  -d '{"chapterId":"ch1","html":"<html>...</html>"}'
```

**注意**：先修改 `worker/auth-worker.js` 中的 `ADMIN_SECRET` 为一个随机字符串。

### 5. 推送前端更新到 GitHub Pages

```bash
git add -A
git commit -m "feat: integrate Cloudflare Worker auth system"
git push
```

## API 文档

### POST /api/login

登录并获取 token。

**请求体：**
```json
{
  "phone": "13800138000",
  "name": "张三",
  "invitationCode": "EBST2026",
  "deviceFingerprint": "sha256hash..."
}
```

**成功响应：**
```json
{
  "success": true,
  "token": "abc123...",
  "name": "张三",
  "expiresAt": 1730000000000
}
```

**设备限制响应：**
```json
{
  "success": false,
  "error": "已在其他设备登录，最多支持 2 台设备。请先在旧设备上退出登录。",
  "code": "DEVICE_LIMIT"
}
```

### GET /api/verify

验证 token 有效性。

**请求头：**
```
Authorization: Bearer {token}
X-Device-Fingerprint: {fingerprint}
```

**成功响应：**
```json
{
  "valid": true,
  "name": "张三",
  "phone": "13800138000"
}
```

### POST /api/logout

登出，清除当前设备指纹。

**请求头：**
```
Authorization: Bearer {token}
X-Device-Fingerprint: {fingerprint}
```

### GET /api/chapter/:id

通过 Worker 代理获取章节 HTML（需 token）。

**请求头：**
```
Authorization: Bearer {token}
```

## 安全机制

| 机制 | 说明 |
|------|------|
| 设备指纹 | 7 维度采集（UA/屏幕/语言/平台/时区/Canvas/WebGL），SHA-256 哈希 |
| Token | phone + timestamp + UUID 的 SHA-256，48 字符 |
| Token 有效期 | 7 天（604800 秒），KV 自动过期 |
| 设备数限制 | 每个手机号最多 2 个设备指纹 |
| 过期设备清理 | 30 天未活跃的设备自动从记录中移除 |
| 反向索引 | token → phone 的 KV 映射，快速验证 |
| CORS | 白名单域名，非允许 origin 无法调用 API |

## KV 数据结构

```
user:{phone}  → {
  phone, name, invitationCode,
  devices: [{ fingerprint, lastSeen, ip, addedAt }],
  token, tokenExpiresAt,
  createdAt, lastLogin, lastLogout
}

token:{token}  → {phone}   (TTL = 7天，自动过期)

chapter:{id}   → HTML 原文  (可选，用于内容保护)
```

## 降级策略

Worker 不可达时（网络问题/Cloudflare 宕机）：
- 登录：回退到 localStorage 本地存储模式
- 验证：回退到本地 token 检查
- 章节访问：直接访问 GitHub Pages 静态文件

## 邀请码管理

当前硬编码在 `worker/auth-worker.js` 的 `VALID_CODES` 集合中：

```javascript
const VALID_CODES = new Set(['EBST2026', '3HFIT-ACE', 'RISE2026', 'COACH-001']);
```

修改后执行 `wrangler deploy` 即可生效。后续可改为从 KV 读取实现动态管理。

## 故障排查

| 问题 | 检查 |
|------|------|
| 登录无响应 | 检查 `js/auth.js` 中 `WORKER_URL` 是否正确 |
| CORS 错误 | 检查 Worker 中 `corsHeaders()` 的 allowed 列表 |
| token 验证失败 | 用 `wrangler kv:key list EBST_AUTH` 查看 KV 数据 |
| 章节 404 | 确认章节已上传到 KV 或使用静态文件直连 |
