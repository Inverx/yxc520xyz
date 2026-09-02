"""账号与绑定设置终端工具：密码、手机号、人脸、微信。

用法：python setting_cli.py [--offline]
"""

import getpass
import json
import os
import sys

from jxxy_client import JxxyClient, ProtocolError, ProtocolResponseError, redact

OFFLINE = "--offline" in sys.argv[1:]


def _code_eq(code, expected) -> bool:
    return code == expected or str(code) == str(expected)


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
    print("1. 修改密码（uppassword）")
    print("2. 发送手机验证码（phonecode）")
    print("3. 手机验证码重置密码（alterphonepasswoed）")
    print("4. 设备 CID 身份校验（getcidpasswoed）")
    print("5. 设备 CID 重置密码（altercidpasswoed）")
    print("6. 修改绑定手机号（upphone）")
    print("7. 更新人脸（uphumanfacealter）")
    print("8. 绑定微信（wxopen）")
    print("9. 解绑微信（wxdelete）")
    choice = input("请选择（1-9）：").strip()

    if choice == "1":
        student = input("学号：").strip()
        password = getpass.getpass("新密码（不回显）：")
        response = _send(client, "uppassword", student_id=student, password=password)
        if response is not None and isinstance(response.data, dict) and _code_eq(response.data.get("data"), 200):
            print("密码修改成功（data=200）")
            return 0
    elif choice == "2":
        phone = input("手机号：").strip()
        response = _send(client, "phonecode", phone=phone)
        if response is not None and isinstance(response.data, dict) and _code_eq(response.data.get("data"), 200):
            print("验证码已发送（data=200）")
            return 0
    elif choice == "3":
        phone = input("手机号：").strip()
        code = input("验证码：").strip()
        response = _send(client, "alterphonepasswoed", phone=phone, code=code)
        if response is not None and _code_eq(response.code, 200):
            print("密码已重置（code=200）")
            return 0
    elif choice == "4":
        student = input("学号：").strip()
        cid = input("设备 CID：").strip()
        response = _send(client, "getcidpasswoed", student_id=student, cid=cid)
        if response is not None and _code_eq(response.code, 2001):
            print("校验成功（code=2001）")
            return 0
    elif choice == "5":
        student = input("学号：").strip()
        cid = input("设备 CID：").strip()
        response = _send(client, "altercidpasswoed", student_id=student, cid=cid)
        if response is not None and isinstance(response.data, dict) and _code_eq(response.data.get("data"), 200):
            print("密码已重置（data=200）")
            return 0
    elif choice == "6":
        student = input("学号：").strip()
        phone = input("新手机号：").strip()
        response = _send(client, "upphone", student_id=student, phone=phone)
    elif choice == "7":
        student = input("学号：").strip()
        url = input("人脸图片 URL：").strip()
        semester = input("学期：").strip()
        response = _send(
            client,
            "uphumanfacealter",
            student_id=student,
            FaceRecognition=url,
            semester=semester,
        )
    elif choice == "8":
        code = input("微信授权码：").strip()
        response = _send(client, "wxopen", code=code)
    elif choice == "9":
        confirm = input("确认解绑微信？(y/N)：").strip().lower()
        if confirm != "y":
            print("已取消")
            return 0
        response = _send(client, "wxdelete")
    else:
        print("无效选择")
        return 2

    if response is None:
        return 1
    print(json.dumps(redact(response.data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
