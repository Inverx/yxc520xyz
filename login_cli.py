"""登录认证终端工具：账号密码 -> Token/UID。

用法：python login_cli.py [--offline]
"""

import getpass
import json
import os
import sys
from pathlib import Path

from jxxy_client import JxxyClient, ProtocolError, ProtocolResponseError, redact

OFFLINE = "--offline" in sys.argv[1:]


def _code_eq(code, expected) -> bool:
    return code == expected or str(code) == str(expected)


def main() -> int:
    student = input("请输入学号：").strip()
    if not student:
        print("学号不能为空")
        return 2
    password = getpass.getpass("请输入密码（不回显）：")
    cid = input("个推 CID（可直接回车）：").strip()
    client = JxxyClient(token="")

    if OFFLINE:
        request = client.build_request(
            "accountLogin", student_id=student, password=password, cid=cid
        )
        print(f"API：accountLogin")
        print(f"方法：{request.method}")
        print(f"地址：{request.url}")
        print(f"请求体：{json.dumps(redact(json.loads(request.json_bytes or b'{}')), ensure_ascii=False)}")
        return 0

    try:
        response = client.login_account(student, password, cid)
    except ProtocolResponseError as error:
        if error.response.session_expired:
            print("会话已失效")
        else:
            print(f"HTTP {error.response.status}（服务端未接受）")
            print(json.dumps(redact(error.response.data), ensure_ascii=False, indent=2))
        return 1
    except ProtocolError as error:
        print(f"网络错误：{error}")
        return 2

    if _code_eq(response.code, 100):
        token = response.data.get("token")
        userid = response.data.get("userid")
        print("登录成功（code=100）")
        print(f"Token：{token}")
        print(f"UID：{userid}")
        save = input("是否保存会话到 session.json？(y/N)：").strip().lower()
        if save == "y":
            Path("session.json").write_text(
                json.dumps({"token": token, "userid": userid}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("已保存：session.json")
        print("提示：其它工具支持环境变量 JXXY_TOKEN，或运行时直接粘贴 Token。")
        return 0
    if _code_eq(response.code, 1001):
        print("账号已被封禁（code=1001）")
        return 1
    print("账号或密码错误")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
