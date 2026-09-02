"""系统消息与未读管理终端工具。

用法：python message_cli.py [--offline]
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
    print("1. 系统消息列表（SystemInfosApi）")
    print("2. 标记消息已读（SystemInfosApi PUT）")
    print("3. 清空未读（SystemInfosApi POST）")
    choice = input("请选择（1-3）：").strip()

    if choice == "1":
        page = input("页码（默认 1）：").strip() or "1"
        response = _send(client, "sysMessageList", page=page)
    elif choice == "2":
        message_id = input("消息 data_id：").strip()
        response = _send(client, "putskipdata", id=message_id)
    elif choice == "3":
        confirm = input("确认清空未读？(y/N)：").strip().lower()
        if confirm != "y":
            print("已取消")
            return 0
        response = _send(client, "clearUnreadList")
    else:
        print("无效选择")
        return 2

    if response is None:
        return 1
    print(json.dumps(redact(response.data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
