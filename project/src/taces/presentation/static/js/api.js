/* 页面唯一的取数出口。接后端时只把 USE_MOCK 改成 false，页面代码不用动。
   mock 的分支和 fetch 的分支返回同一种形状：接口的 data 部分，出错则抛 APIError。 */
window.API = (() => {
  'use strict';

  const USE_MOCK = true;
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
    const entry = window.MOCK ? window.MOCK[path] : undefined;
    if (entry === undefined) {
      throw new APIError(404, 'NOT_FOUND', '没有这个接口。');
    }
    const value = typeof entry === 'function' ? entry(body, method) : entry;
    if (value && value.__error) {
      throw new APIError(value.__error.status, value.__error.code, value.__error.message);
    }
    return value;
  }

  async function fromServer(path, method, body) {
    const headers = { 'X-TACES-Request': '1' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();

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

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = payload.error || {};
      throw new APIError(
        response.status,
        error.code || `HTTP_${response.status}`,
        error.message || '请求失败，请稍后重试。',
      );
    }
    return payload.data;
  }

  function request(method, path, body) {
    return USE_MOCK ? fromMock(path, method, body) : fromServer(path, method, body);
  }

  return {
    USE_MOCK,
    APIError,
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body),
  };
})();
