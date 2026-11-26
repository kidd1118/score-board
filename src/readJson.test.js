import { readJson } from './readJson';

const response = (status, text) => ({
  ok: status < 400,
  status,
  statusText: 'Error',
  json: () => Promise.resolve().then(() => JSON.parse(text)),
});

test('returns the parsed body', async () => {
  await expect(readJson(response(200, '{"a":1}'))).resolves.toEqual({ a: 1 });
});

test('uses the API error detail', async () => {
  await expect(readJson(response(502, '{"detail":"NBA 掛了"}'))).rejects.toMatchObject({ message: 'NBA 掛了', status: 502 });
});

test('explains a proxy error page instead of a JSON syntax error', async () => {
  const proxyError = 'Proxy error: Could not proxy request /games/ from localhost:3000 to http://localhost:8000.';
  await expect(readJson(response(500, proxyError))).rejects.toMatchObject({
    message: '連不上後端伺服器（HTTP 500），請確認後端有啟動',
    status: 500,
  });
});
