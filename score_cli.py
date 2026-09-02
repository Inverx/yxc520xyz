"""学期成绩与加分记录查询终端工具。

用法：python score_cli.py [--offline]
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
    response = _send(client, "semesterLists")
    if response is None:
        return 1

    data = response.data.get("data") if isinstance(response.data, dict) else None
    semesters = (data or {}).get("all_semesters") if isinstance(data, dict) else None
    if isinstance(semesters, list) and semesters:
        for index, name in enumerate(semesters, 1):
            print(f"{index}. {name}")
        choice = input("选择学期（序号或学期名）：").strip()
        try:
            semester = semesters[int(choice) - 1]
        except (ValueError, IndexError):
            semester = choice
    else:
        semester = input("请输入学期（例如 2025-2026-1）：").strip()
    if not semester:
        print("学期不能为空")
        return 2

    grades = _send(client, "yeargrades", semester=semester)
    if grades is None:
        return 1
    print(f"学期 {semester} 成绩（code={grades.code}）：")
    print(json.dumps(redact(grades.data), ensure_ascii=False, indent=2))

    more = input("是否查询加分记录？(y/N)：").strip().lower()
    if more == "y":
        page = input("页码（默认 1）：").strip() or "1"
        records = _send(client, "getAddPointList", page=page)
        if records is not None:
            print(json.dumps(redact(records.data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
