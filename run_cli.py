"""校园跑打卡提交终端工具：自动生成签名并上传跑步记录。

用法：python run_cli.py [--offline]
"""

import json
import os
import sys
from datetime import datetime

from jxxy_client import (
    JxxyClient,
    ProtocolError,
    ProtocolResponseError,
    RunRecord,
    redact,
)

OFFLINE = "--offline" in sys.argv[1:]


def _code_eq(code, expected) -> bool:
    return code == expected or str(code) == str(expected)


def _token() -> str:
    env = os.environ.get("JXXY_TOKEN", "").strip()
    return env or input("请输入 Token：").strip()


def main() -> int:
    client = JxxyClient(token=_token())
    now = datetime.now()

    student = input("请输入学号：").strip()
    semester = input("请输入学期（例如 2025-2026-1）：").strip()
    distance = input("请输入距离（公里，例如 3.20）：").strip()
    pace = input("请输入配速（例如 5.30）：").strip()
    running_time = input("跑步时长（默认 00:00:00）：").strip() or "00:00:00"
    step_count = input("步数（默认 0）：").strip() or "0"
    start_time = (
        input(f"开始时间（默认 {now.strftime('%Y-%m-%d %H:%M:%S')}）：").strip()
        or now.strftime("%Y-%m-%d %H:%M:%S")
    )
    end_time = (
        input(f"结束时间（默认 {now.strftime('%Y-%m-%d %H:%M:%S')}）：").strip()
        or now.strftime("%Y-%m-%d %H:%M:%S")
    )
    qualified = input("是否合格（默认 Y）：").strip().lower() != "n"
    submitted_at = (
        input(f"提交日期（默认 {now.strftime('%Y-%m-%d')}）：").strip()
        or now.strftime("%Y-%m-%d")
    )
    track_file = input("轨迹 JSON 文件路径（可空，默认 []）：").strip()
    if track_file:
        try:
            track = json.loads(open(track_file, encoding="utf-8").read())
        except (OSError, json.JSONDecodeError) as error:
            print(f"轨迹文件读取失败：{error}")
            return 2
    else:
        track = []

    record = (
        RunRecord.builder()
        .running_time(running_time)
        .student(student)
        .distance(distance)
        .pace(pace)
        .track(track)
        .step_count(int(step_count))
        .start_time(start_time)
        .end_time(end_time)
        .is_qualified(qualified)
        .semester(semester)
        .submitted_at(submitted_at)
        .build()
    )

    print(f"签名：{record.signature()}")
    request = client.build_request(
        "uploadRunList", signature=record.signature(), **record.as_kwargs()
    )
    print(f"方法：{request.method}")
    print(f"地址：{request.url}")
    print(f"请求体：{json.dumps(redact(json.loads(request.json_bytes or b'{}')), ensure_ascii=False, indent=2)}")
    if OFFLINE:
        print("离线模式：未发送")
        return 0

    try:
        response = client.upload_run(record)
    except ProtocolResponseError as error:
        if error.response.session_expired:
            print("会话已失效，请重新登录")
        else:
            print(f"HTTP {error.response.status}（服务端未接受）")
            print(json.dumps(redact(error.response.data), ensure_ascii=False, indent=2))
        return 1
    except ProtocolError as error:
        print(f"网络错误：{error}")
        return 2

    if _code_eq(response.code, 2001):
        print("上传成功（code=2001）")
        return 0
    if _code_eq(response.code, 2002):
        print("服务端拒绝：签名错误（code=2002）")
        return 1
    if _code_eq(response.code, 2003):
        print("服务端提示停止（code=2003）")
        return 1
    print(f"上传结果：code={response.code}")
    print(json.dumps(redact(response.data), ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
