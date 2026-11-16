from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus

from aiohttp import web


@dataclass
class StaticPathConfig:
    url_path: str
    path: str
    cache_headers: bool = True


class HomeAssistantView:
    url: str = ""
    name: str = ""
    requires_auth = True
    extra_urls: list[str] = []

    @staticmethod
    def json(result, status_code: int = HTTPStatus.OK, headers=None) -> web.Response:
        return web.Response(text=json.dumps(result, ensure_ascii=False, default=str), status=int(status_code),
                            content_type="application/json", headers=headers)

    def json_message(self, message: str, status_code: int = HTTPStatus.OK, message_code=None, headers=None) -> web.Response:
        body = {"message": message}
        if message_code:
            body["code"] = message_code
        return self.json(body, status_code, headers)
