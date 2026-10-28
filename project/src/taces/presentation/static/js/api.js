/* 页面唯一的取数出口。默认连接真实后端，静态原型调试可手动启用 USE_MOCK。
   mock 的分支和 fetch 的分支返回同一种形状：接口的 data 部分，出错则抛 APIError。 */
window.API = (() => {
  'use strict';

  const USE_MOCK = false;
  const MOCK_LATENCY = 120;

  class APIError extends Error {
    constructor(status, code, message) {
      super(message);
      this.name = 'APIError';
      this.status = status;
      this.code = code;
    }
  }

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  async function fromMock(path, method, body) {
    await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY));
    // mock 的键是路径本身，查询串单独交给取值函数
    const [route, query] = path.split('?');
    const entry = window.MOCK ? window.MOCK[route] : undefined;
    if (entry === undefined) {
      throw new APIError(404, 'NOT_FOUND', '没有这个接口。');
    }
    const params = new URLSearchParams(query || '');
    const value = typeof entry === 'function' ? entry(body, method, params) : entry;
    if (value && value.__error) {
      throw new APIError(value.__error.status, value.__error.code, value.__error.message);
    }
    return value;
  }

  async function fromServer(path, method, body, binary = false) {
    const headers = { 'X-TACES-Request': '1' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    // 学生端的写接口没有会话可绑 CSRF（见 API_CONTRACT.md），没 token 就不发这个头
    const token = csrfToken();
    if (method !== 'GET' && token) headers['X-CSRF-Token'] = token;

    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        credentials: 'include',
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      throw new APIError(0, 'NETWORK_ERROR', '连不上服务，检查网络后重试。');
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = payload.error || {};
      throw new APIError(
        response.status,
        error.code || `HTTP_${response.status}`,
        error.message || '请求失败，请稍后重试。',
      );
    }
    if (binary) {
      const blob = await response.blob();
      if (binary !== 'metadata') return blob;
      const disposition = response.headers.get('Content-Disposition') || '';
      const match = /(?:^|;)\s*filename="?(statistics-[0-9a-f]{32}\.(?:csv|pdf))"?\s*(?:;|$)/i.exec(disposition);
      return { blob, filename: match ? match[1] : null };
    }
    const payload = await response.json().catch(() => ({}));
    return payload.data;
  }

  function request(method, path, body) {
    return USE_MOCK ? fromMock(path, method, body) : fromServer(path, method, body);
  }

  return {
    USE_MOCK,
    APIError,
    request,
    get: (path) => request('GET', path),
    download: (path) => USE_MOCK
      ? Promise.reject(new APIError(501, 'MOCK_UNAVAILABLE', '模拟模式不支持导出，请连接实际服务。'))
      : fromServer(path, 'GET', undefined, true),
    downloadWithMetadata: (path) => USE_MOCK
      ? Promise.reject(new APIError(501, 'MOCK_UNAVAILABLE', '模拟模式不支持导出，请连接实际服务。'))
      : fromServer(path, 'GET', undefined, 'metadata'),
    post: (path, body) => request('POST', path, body),
    patch: (path, body) => request('PATCH', path, body),
  };
})();
