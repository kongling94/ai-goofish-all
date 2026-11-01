import os
import time
import httpx


class SellerError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class SellerClient:
    def __init__(self, base_url=None, username=None, password=None, transport=None, service_token=None):
        self.base_url = base_url or os.getenv('SELLER_URL', 'http://seller-engine:8090')
        self.username = username or os.getenv('SELLER_USERNAME', 'admin')
        self.password = password or os.getenv('SELLER_PASSWORD', '')
        self.transport = transport
        self.service_token = service_token or os.getenv("SELLER_SERVICE_TOKEN", "")
        self._cached_token = None
        self._token_expires_at = 0

    def _is_token_valid(self):
        return self._cached_token and time.time() < self._token_expires_at - 60

    async def _login(self, client):
        login = await client.post('/all/service-login', headers={'X-All-Service-Token': self.service_token}, json={'username': self.username, 'password': self.password})
        if login.status_code != 200:
            raise SellerError(502, '卖家服务认证不可用')
        session = login.json()
        if not session.get('success') or not session.get('token'):
            raise SellerError(502, '卖家服务认证失败，请检查服务端配置')
        self._cached_token = session['token']
        # Assume 1 hour validity if not specified; adjust based on actual seller token lifetime
        self._token_expires_at = time.time() + 3600
        return self._cached_token

    async def request(self, method, path, payload=None):
        async with httpx.AsyncClient(base_url=self.base_url, transport=self.transport, timeout=180) as client:
            if not self._is_token_valid():
                await self._login(client)
            headers = {'Authorization': 'Bearer ' + self._cached_token}
            response = await client.request(method, path, json=payload, headers=headers)
            if response.status_code == 401:
                # Token expired, re-login once
                await self._login(client)
                headers = {'Authorization': 'Bearer ' + self._cached_token}
                response = await client.request(method, path, json=payload, headers=headers)
            if response.status_code >= 400:
                raise SellerError(response.status_code, f'卖家服务拒绝操作（HTTP {response.status_code}），请检查卖家日志')
            result = response.json()
            if isinstance(result, dict) and result.get('success') is False:
                raise SellerError(400, '卖家服务未完成操作，请检查卖家日志')
            return result
