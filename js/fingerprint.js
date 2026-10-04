/**
 * EBST Device Fingerprint — 纯 JS 浏览器指纹采集
 * 不依赖外部库，生成 SHA-256 哈希作为设备唯一标识
 *
 * 采集维度:
 *   - navigator.userAgent
 *   - screen 分辨率
 *   - navigator.language
 *   - navigator.platform
 *   - 时区偏移
 *   - Canvas fingerprint
 *   - WebGL renderer/vendor
 *   - 字体检测（5 个常见字体）
 */

async function generateFingerprint() {
  const components = [];

  // 1. User Agent
  components.push(navigator.userAgent || '');

  // 2. Screen resolution
  components.push(`${screen.width}x${screen.height}`);

  // 3. Language
  components.push(navigator.language || '');

  // 4. Platform
  components.push(navigator.platform || '');

  // 5. Timezone offset (minutes)
  components.push(String(new Date().getTimezoneOffset()));

  // 6. Canvas fingerprint
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 50;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.textBaseline = 'top';
      ctx.font = "14px 'Arial'";
      ctx.fillStyle = '#f60';
      ctx.fillRect(0, 0, 100, 20);
      ctx.fillStyle = '#069';
      ctx.fillText('EBST-fp:canvas!', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('EBST-fp:canvas!', 4, 17);
      components.push(canvas.toDataURL());
    }
  } catch (e) {
    components.push('canvas-unsupported');
  }

  // 7. WebGL renderer & vendor
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (debugInfo) {
        components.push(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || '');
        components.push(gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) || '');
      } else {
        components.push(gl.getParameter(gl.RENDERER) || '');
        components.push(gl.getParameter(gl.VENDOR) || '');
      }
    }
  } catch (e) {
    // WebGL not available
  }

  // 8. Font detection (5 common fonts)
  try {
    const testFonts = ['Arial', 'Times New Roman', 'Courier New', 'Verdana', 'Georgia'];
    const baseFonts = ['monospace', 'sans-serif', 'serif'];
    const testString = 'mmmmmmmmlli';
    const testSize = '72px';

    const span = document.createElement('span');
    span.style.position = 'absolute';
    span.style.left = '-9999px';
    span.style.fontSize = testSize;
    span.textContent = testString;

    const baseWidths = {};
    for (const bf of baseFonts) {
      span.style.fontFamily = bf;
      document.body.appendChild(span);
      baseWidths[bf] = span.offsetWidth;
      document.body.removeChild(span);
    }

    const detected = [];
    for (const font of testFonts) {
      let found = false;
      for (const bf of baseFonts) {
        span.style.fontFamily = `'${font}', ${bf}`;
        document.body.appendChild(span);
        if (span.offsetWidth !== baseWidths[bf]) {
          found = true;
        }
        document.body.removeChild(span);
        if (found) break;
      }
      if (found) detected.push(font);
    }
    components.push(detected.join(','));
  } catch (e) {
    // Font detection failed
  }

  // 9. Color depth & pixel ratio
  components.push(`${screen.colorDepth}-${window.devicePixelRatio}`);

  // 10. Hardware concurrency
  components.push(String(navigator.hardwareConcurrency || ''));

  // Hash all components → SHA-256
  const raw = components.join('|');
  const encoder = new TextEncoder();
  const data = encoder.encode(raw);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

  return hashHex;
}

// Export for use in other scripts
window.EBSTFingerprint = { generate: generateFingerprint };
