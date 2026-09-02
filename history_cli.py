"""历史跑步记录查询终端工具。

用法：python history_cli.py [--offline]
"""

import json
import os
import sys

from jxxy_client import JxxyClient, ProtocolError, ProtocolResponseError, redact

OFFLINE = "--offline" in sys.argv[1:]


def _token() -> str:
    env = os.environ.get("JXXY_TOKEN", "").strip()
    return env or input("请输入 Token：").strip()


def _send(client: JxxyClient, api_name: str, **params):
    if OFFLINE:
        request = client.build_request(api_name, **params)
        print(f"API：{api_name}  方法：{request.method}  地址：{request.url}")
        return None
    try:
        return client.execute(api_name, **params)
    except ProtocolResponseError as error:
        if error.response.session_expired:
            print("会话已失效，请重新登录")
        else:
            print(f"HTTP {error.response.status}（服务端未接受）")
            print(json.dumps(redact(error.response.data), ensure_ascii=False, indent=2))
        return None
    except ProtocolError as error:
        print(f"网络错误：{error}")
        return None


def main() -> int:
    client = JxxyClient(token=_token())
    student = input("请输入学号：").strip()
    page = input("页码（默认 1）：").strip() or "1"
    while True:
        response = _send(client, "myrunings", student=student, page=page)
        if response is None:
            return 1
        data = response.data if isinstance(response.data, dict) else {}
        results = data.get("results") if isinstance(data, dict) else None
        if isinstance(results, list):
            print(f"第 {page} 页，共 {len(results)} 条：")
        else:
            print("响应：")
        print(json.dumps(redact(response.data), ensure_ascii=False, indent=2))
        has_next = bool(isinstance(data, dict) and data.get("next"))
        if not has_next:
            print("已到最后一页")
            break
        more = input("继续下一页？(y/N)：").strip().lower()
        if more != "y":
            break
        page = str(int(page) + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
