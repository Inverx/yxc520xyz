"""学校通知公告、首页导航与环境检测查询终端工具。

用法：python policy_cli.py [--offline]
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
    print("1. 首页导航（FlushedApi）")
    print("2. 通知公告汇总（FlushedTApi）")
    print("3. 通知历史（AnnouncementApi）")
    print("4. 环境检测（InformationApi）")
    print("5. 服务器时间（apitime）")
    print("6. 版本检查（VersionApi）")
    choice = input("请选择（1-6）：").strip()

    if choice == "1":
        response = _send(client, "allnavlists")
    elif choice == "2":
        response = _send(client, "allinforms")
    elif choice == "3":
        page = input("页码（默认 1）：").strip() or "1"
        response = _send(client, "histnotices", page=page)
    elif choice == "4":
        all_app = input("应用列表（分号分隔，可空）：").strip()
        app_version = input("系统版本（可空）：").strip()
        app_factory = input("设备厂商型号（可空）：").strip()
        response = _send(
            client,
            "checkenvironment",
            all_app=all_app,
            App_Version=app_version,
            App_factory=app_factory,
        )
    elif choice == "5":
        response = _send(client, "isServerTimes")
    elif choice == "6":
        platform = input("平台（例如 android）：").strip()
        version = input("客户端版本（例如 1.0.13）：").strip()
        response = _send(client, "getAppVersion", platform=platform, version=version)
    else:
        print("无效选择")
        return 2

    if response is None:
        return 1
    print(json.dumps(redact(response.data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
