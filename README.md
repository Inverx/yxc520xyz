# 健行校园 App (v1.0.13) 纯 Python 协议

纯 Python 标准库实现的健行校园业务协议客户端，覆盖打包脚本中的全部 61 个业务接口，脱离 Android App 与 Native SO 依赖。所有功能模块均独立解耦，终端输入对应参数与凭据（Token/UID）即可独立执行。

---

## 一、环境安装

1. 要求 Python 3.10+。
2. 无需安装任何依赖（仅标准库）。

```powershell
python --version
```

## 二、独立模块运行指南

### 1. 登录认证换取凭证 (`login_cli.py`)

终端输入账号与密码（密码不回显），输出登录成功/失败响应面板及 Token、UID，可选择保存会话到 `session.json`：

```powershell
python login_cli.py
```

### 2. 学期成绩与加分记录查询 (`score_cli.py`)

输入 Token，列出学期并查询指定学期成绩，可继续查询加分记录：

```powershell
python score_cli.py
```

### 3. 校园跑打卡提交 (`run_cli.py`)

输入 Token、学号、学期及跑步距离与配速，自动生成 HMAC-SHA256 签名并提交跑步记录；加 `--offline` 只打印请求不发送：

```powershell
python run_cli.py --offline
```

### 4. 历史跑步记录查询 (`history_cli.py`)

输入 Token 与学号，分页查询历史跑步记录：

```powershell
python history_cli.py
```

### 5. 个人跑步数据与结算统计 (`stats_cli.py`)

输入 Token，查询个人跑步数据（MyDataApi）与指定日期结算统计（RunStatsAPI）：

```powershell
python stats_cli.py
```

### 6. 通知公告、首页导航与环境检测 (`policy_cli.py`)

输入 Token，查询首页导航、通知公告汇总与历史、环境检测、服务器时间与版本检查：

```powershell
python policy_cli.py
```

### 7. 系统消息管理 (`message_cli.py`)

输入 Token，分页查询系统消息、标记已读与清空未读：

```powershell
python message_cli.py
```

### 8. 活动与赛事查询 (`activity_cli.py`)

输入 Token，分页查询活动列表（type=活动）与赛事列表（type=赛事）：

```powershell
python activity_cli.py
```

### 9. 账号与绑定设置 (`setting_cli.py`)

输入 Token，修改密码、手机验证码重置、设备 CID 校验与重置、修改绑定手机号、更新人脸、微信绑定与解绑：

```powershell
python setting_cli.py
```

> 提示：所有工具均支持环境变量 `JXXY_TOKEN`；设置后运行工具将自动读取，无需手动粘贴。

## 三、模块架构与文件清单

| 文件 | 说明 |
| --- | --- |
| `jxxy_client.py` | 核心协议客户端：61 个接口目录、请求构造、会话 Header、`detail=499` 会话失效判定与跑步签名计算器。 |
| `login_cli.py` | 登录认证终端工具（账号密码 -> 输出 Token/UID）。 |
| `score_cli.py` | 学期成绩与加分记录查询工具。 |
| `run_cli.py` | 校园跑打卡提交工具（自动生成 HMAC-SHA256 签名并上传跑步记录）。 |
| `history_cli.py` | 历史跑步记录查询工具。 |
| `stats_cli.py` | 个人跑步数据与结算统计查询工具。 |
| `policy_cli.py` | 通知公告、首页导航与环境检测查询工具。 |
| `message_cli.py` | 系统消息与未读管理工具。 |
| `activity_cli.py` | 活动与赛事列表查询工具。 |
| `setting_cli.py` | 密码、手机号、人脸与微信绑定设置工具。 |
| `requirements.txt` | 运行依赖清单（无第三方依赖）。 |

## 说明

- 接口清单、字段与签名算法提取自公开分发的 APK 客户端脚本；签名密钥随客户端分发，本就不具备保密性。
- 登录与跑步上传等写操作需要有效账号；本项目不提供、不猜测账号。
