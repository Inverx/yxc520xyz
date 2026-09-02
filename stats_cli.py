"""个人跑步数据与结算统计查询终端工具。

用法：python stats_cli.py [--offline]
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
    response = _send(client, "getRuningData")
    if response is None:
        return 1
    print("我的跑步数据：")
    print(json.dumps(redact(response.data), ensure_ascii=False, indent=2))

    submitted_at = input("请输入结算日期（例如 2026-01-02）：").strip()
    if submitted_at:
        stats = _send(client, "runtendata", time=submitted_at)
        if stats is None:
            return 1
        print(f"{submitted_at} 结算统计：")
        print(json.dumps(redact(stats.data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
