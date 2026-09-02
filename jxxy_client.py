"""健行校园 App (v1.0.13) 纯 Python 协议核心（纯标准库，无第三方依赖）。

单文件共享内核，供各独立 CLI 模块调用：
- 请求构造：61 个业务接口的 method/path/query/body 契约（对应打包脚本 API 模块）
- 会话：Authorization Header、HTTP 状态与 detail=499 会话失效判定
- 签名：跑步记录 Signature = HMAC-SHA256(固定密钥, 五字段消息)，输出小写十六进制
- 门面：JxxyClient 提供各业务用例方法
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping

BASE_URL = "https://xcsport.hhtc.edu.cn:9443"
RUN_SIGNATURE_KEY = "jdjdj-hfjfjh5681"
DEFAULT_TIMEOUT = 5.0

SENSITIVE_FIELDS = {"token", "userid", "password", "access_token", "openid"}


class ProtocolError(Exception):
    """协议基础错误。"""


class ProtocolInputError(ProtocolError):
    """缺少应用协议要求的字段。"""


class ProtocolResponseError(ProtocolError):
    """HTTP 或会话响应被应用协议拒绝。"""

    def __init__(self, response: "ProtocolResponse") -> None:
        self.response = response
        reason = (
            "session expired" if response.session_expired else f"HTTP {response.status}"
        )
        super().__init__(reason)


def _js_string(value: Any) -> str:
    """匹配原包 JavaScript 的字符串拼接语义，用于签名与查询参数。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if value.is_integer():
            return str(int(value))
    return str(value)


def redact(value: Any) -> Any:
    """递归脱敏响应数据。"""
    if isinstance(value, dict):
        return {
            key: "<已隐藏>" if key.lower() in SENSITIVE_FIELDS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def build_run_signature_message(
    start_time: Any,
    is_qualified: Any,
    student: Any,
    distance: Any,
    pace: Any,
) -> str:
    return "_".join(
        _js_string(value)
        for value in (start_time, is_qualified, student, distance, pace)
    )


def sign_running_record(
    start_time: Any,
    is_qualified: Any,
    student: Any,
    distance: Any,
    pace: Any,
    key: str = RUN_SIGNATURE_KEY,
) -> str:
    message = build_run_signature_message(
        start_time, is_qualified, student, distance, pace
    )
    return hmac.new(
        key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


@dataclass(frozen=True)
class ProtocolRequest:
    """请求 DTO：由 Builder 生成，可离线审查，也可交给 Transport 发送。"""

    api_name: str
    method: str
    url: str
    headers: Mapping[str, str]
    body: Mapping[str, Any] | None
    timeout: float

    @property
    def json_bytes(self) -> bytes | None:
        if self.body is None:
            return None
        return json.dumps(
            self.body, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    def to_urllib_request(self) -> urllib.request.Request:
        return urllib.request.Request(
            self.url,
            data=self.json_bytes,
            method=self.method,
            headers=dict(self.headers),
        )


@dataclass(frozen=True)
class ProtocolResponse:
    """响应 DTO：HTTP 状态、解析后的 JSON 数据、会话失效标记。"""

    status: int
    data: Any
    raw_body: bytes
    session_expired: bool

    @property
    def accepted(self) -> bool:
        return 200 <= self.status < 300 and not self.session_expired

    @property
    def code(self) -> Any:
        return self.data.get("code") if isinstance(self.data, dict) else None

    @property
    def detail(self) -> Any:
        return self.data.get("detail") if isinstance(self.data, dict) else None

    def ensure_accepted(self) -> "ProtocolResponse":
        if not self.accepted:
            raise ProtocolResponseError(self)
        return self


def parse_response(status: int, body: bytes | str, token: str = "") -> ProtocolResponse:
    """解析响应；仅当请求携带 token 且业务 detail=499 时标记会话失效。"""
    raw = body.encode("utf-8") if isinstance(body, str) else body
    text = raw.decode("utf-8", errors="replace")
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        data = text
    detail = data.get("detail") if isinstance(data, dict) else None
    expired = bool(token) and _js_string(detail) == "499"
    return ProtocolResponse(status, data, raw, expired)


class Transport:
    """标准库传输；只发送调用方明确指定的请求，不自动登录、不重试、不串联流程。"""

    def send(
        self,
        request: ProtocolRequest,
        ssl_context: ssl.SSLContext | None = None,
    ) -> ProtocolResponse:
        context = ssl_context or ssl.create_default_context()
        try:
            with urllib.request.urlopen(
                request.to_urllib_request(),
                timeout=request.timeout,
                context=context,
            ) as response:
                result = parse_response(
                    response.status,
                    response.read(),
                    request.headers["Authorization"],
                )
        except urllib.error.HTTPError as error:
            result = parse_response(
                error.code,
                error.read(),
                request.headers["Authorization"],
            )
        except urllib.error.URLError as error:
            raise ProtocolError(f"network error: {error.reason}") from error
        return result.ensure_accepted()


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    required: tuple[str, ...] = ()
    path_fields: tuple[str, ...] = ()
    query_fields: tuple[tuple[str, str], ...] = ()
    query_all: bool = False
    body_fields: tuple[tuple[str, str], ...] = ()
    body_all: bool = False
    fixed_query: Mapping[str, Any] = field(default_factory=dict)
    fixed_body: Mapping[str, Any] = field(default_factory=dict)
    timeout: float = DEFAULT_TIMEOUT


def _endpoint(
    method: str,
    path: str,
    *,
    required: tuple[str, ...] = (),
    path_fields: tuple[str, ...] = (),
    query: tuple[tuple[str, str], ...] = (),
    query_all: bool = False,
    body: tuple[tuple[str, str], ...] = (),
    body_all: bool = False,
    fixed_query: Mapping[str, Any] | None = None,
    fixed_body: Mapping[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Endpoint:
    return Endpoint(
        method=method.upper(),
        path=path,
        required=required,
        path_fields=path_fields,
        query_fields=query,
        query_all=query_all,
        body_fields=body,
        body_all=body_all,
        fixed_query=fixed_query or {},
        fixed_body=fixed_body or {},
        timeout=timeout,
    )


# 接口目录：webpack API 模块 99e7 的全部 61 个导出。
# 名称保留原包拼写（例如 alterphonepasswoed、getRuningData），便于逐条核对。
ENDPOINTS: dict[str, Endpoint] = {
    "phonecode": _endpoint("GET", "/PhoneUpdatePasswordApi/", required=("phone",), query=(("phone", "phone"),)),
    "alterphonepasswoed": _endpoint("POST", "/PhoneUpdatePasswordApi/", required=("phone", "code"), body=(("phone", "phone"), ("code", "code"))),
    "cosdata": _endpoint("GET", "/moment/", required=("userid",), query=(("student_id", "userid"),), query_all=True),
    "userinfo": _endpoint("GET", "/user/{student_id}/", path_fields=("student_id",)),
    "actAddPoints": _endpoint("GET", "/AddUploadVoucherAdApi/", required=("page",), query=(("page", "page"),)),
    "actAddlists": _endpoint("GET", "/AddUploadVoucherAdApi/", required=("id",), query=(("id", "id"),)),
    "provetype": _endpoint("GET", "/TypeApi/", query_all=True),
    "voucherpush": _endpoint("POST", "/Voucher/", body_all=True),
    "vouchergain": _endpoint("GET", "/Voucher/", required=("student_id", "page"), query=(("student", "student_id"), ("page", "page"))),
    "homeinfo": _endpoint("GET", "/HomeInfo/"),
    "flushinfo": _endpoint("GET", "/FlushedApi/"),
    "yearlists": _endpoint("GET", "/YearsLsit/"),
    "infogrades": _endpoint("GET", "/Grades/"),
    "infotachs": _endpoint("GET", "/TchName/"),
    "potuserinfo": _endpoint("PUT", "/user/{student_id}/", required=("student_id", "teacher", "time"), path_fields=("student_id",), body=(("teacher", "teacher"), ("lecture_time", "time"))),
    "fitnessdata": _endpoint("POST", "/MemberCheckIn/", required=("running_time", "student", "track", "start_time", "end_time", "is_qualified", "error"), body=(("running_time", "running_time"), ("student", "student"), ("track", "track"), ("start_time", "start_time"), ("end_time", "end_time"), ("is_qualified", "is_qualified"), ("bu_con", "bu_con"), ("error", "error"))),
    "uppictures": _endpoint("PUT", "/RunningRecord/{id}/", required=("id", "img_url"), path_fields=("id",), body=(("img_url", "img_url"),)),
    "faceverify": _endpoint("POST", "/FaceRecognitionApi/", required=("id", "UrlB"), query=(("data_id", "id"),), body=(("UrlB", "UrlB"),)),
    "myfitness": _endpoint("GET", "/MemberCheckIn/", query_all=True),
    "getDeepSeekinfo": _endpoint("POST", "/DeepSeekChatApi/", required=("id",), body=(("id", "id"),), timeout=120.0),
    "testapi": _endpoint("POST", "/test/", required=("test",), body=(("test", "test"),)),
    "feedbackdata": _endpoint("POST", "/feedbackApi/", required=("student", "information", "description", "imgs", "type"), body=(("student", "student"), ("Contact_information", "information"), ("description", "description"), ("img_src", "imgs"), ("feedback_type", "type"))),
    "getviolation": _endpoint("GET", "/ViolationApi/"),
    "delviolation": _endpoint("DELETE", "/ViolationApi/", required=("id",), body=(("id", "id"),)),
    "appealviolation": _endpoint("PUT", "/ViolationApi/", required=("id", "content"), body=(("id", "id"), ("content", "content"))),
    "getappealviolation": _endpoint("PUT", "/ViolationApi/", fixed_body={"type": 1}),
    "bindingphysicalinfrom": _endpoint("POST", "/PhysicalApi/", required=("user_id", "name", "id_card", "img_url", "semester", "Running_id", "start_time"), body=(("user_id", "user_id"), ("name", "name"), ("id_card", "id_card"), ("img_url", "img_url"), ("semester", "semester"), ("Running_id", "Running_id"), ("start_time", "start_time"))),
    "physicalfaceverify": _endpoint("POST", "/FaceRecognitionApi/", required=("UrlB",), body=(("UrlB", "UrlB"),)),
    "physicalActList": _endpoint("GET", "/PhysicalRunningApi/", fixed_query={"serial_number": "A001"}),
    "getAdvertisingLists": _endpoint("GET", "/HomeAdvertisingApi/"),
    "accountLogin": _endpoint("POST", "/user/login/", required=("student_id", "password", "cid"), body=(("student_id", "student_id"), ("password", "password"), ("cid", "cid"))),
    "wxlogin": _endpoint("POST", "/user/login/", required=("code", "cid"), body=(("code", "code"), ("cid", "cid"))),
    "uppassword": _endpoint("PUT", "/user/{student_id}/", required=("student_id", "password"), path_fields=("student_id",), body=(("password", "password"),)),
    "getcidpasswoed": _endpoint("GET", "/CidUpdatePasswordApi/", required=("student_id", "cid"), query=(("student_id", "student_id"), ("cid", "cid"))),
    "altercidpasswoed": _endpoint("POST", "/CidUpdatePasswordApi/", required=("student_id", "cid"), body=(("student_id", "student_id"), ("cid", "cid"))),
    "getAppVersion": _endpoint("GET", "/VersionApi/", required=("platform", "version"), query=(("platform", "platform"), ("version", "version"))),
    "tokenToUser": _endpoint("GET", "/TokenApi/"),
    "allnavlists": _endpoint("GET", "/FlushedApi/"),
    "allinforms": _endpoint("GET", "/FlushedTApi/"),
    "checkenvironment": _endpoint("POST", "/InformationApi/", required=("all_app", "App_Version", "App_factory"), body=(("all_app", "all_app"), ("App_Version", "App_Version"), ("App_factory", "App_factory"))),
    "activityInfos": _endpoint("GET", "/ActivityInfo/", required=("page",), query=(("page", "page"),), fixed_query={"type": "活动"}),
    "competitionInfos": _endpoint("GET", "/ActivityInfo/", required=("page",), query=(("page", "page"),), fixed_query={"type": "赛事"}),
    "sysMessageList": _endpoint("GET", "/SystemInfosApi/", required=("page",), query=(("page", "page"),)),
    "putskipdata": _endpoint("PUT", "/SystemInfosApi/", required=("id",), query=(("data_id", "id"),)),
    "clearUnreadList": _endpoint("POST", "/SystemInfosApi/"),
    "histnotices": _endpoint("GET", "/AnnouncementApi/", required=("page",), query=(("page", "page"),)),
    "gethelpLists": _endpoint("GET", "/FeedbackAd/"),
    "services": _endpoint("GET", "/CustomerInformationApi/"),
    "answers": _endpoint("GET", "/FeedbackAd/", required=("id",), query=(("id", "id"),)),
    "getRuningData": _endpoint("GET", "/MyDataApi/"),
    "semesterLists": _endpoint("GET", "/SemesterListApi/"),
    "yeargrades": _endpoint("GET", "/Grades/", required=("semester",), query=(("semester", "semester"),)),
    "getAddPointList": _endpoint("GET", "/SemesterGradesApi/", required=("page",), query=(("page", "page"),)),
    "myrunings": _endpoint("GET", "/RunningRecord/", required=("student", "page"), query=(("student", "student"), ("page", "page"))),
    "isServerTimes": _endpoint("GET", "/apitime/"),
    "uploadRunList": _endpoint("POST", "/RunningRecord/", required=("running_time", "student", "distance", "pace", "track", "Step_count", "start_time", "end_time", "is_qualified", "semester", "submitted_at"), body=(("running_time", "running_time"), ("student", "student"), ("distance", "distance"), ("pace", "pace"), ("track", "track"), ("Step_count", "Step_count"), ("start_time", "start_time"), ("end_time", "end_time"), ("is_qualified", "is_qualified"), ("semester", "semester"), ("submitted_at", "submitted_at"))),
    "runtendata": _endpoint("GET", "/RunStatsAPI/", required=("time",), query=(("submitted_at", "time"),)),
    "wxdelete": _endpoint("DELETE", "/WxOpenid/", body_all=True),
    "wxopen": _endpoint("POST", "/WxOpenid/", required=("code",), body=(("code", "code"),)),
    "upphone": _endpoint("PUT", "/user/{student_id}/", required=("student_id", "phone"), path_fields=("student_id",), body=(("phone", "phone"),)),
    "uphumanfacealter": _endpoint("PUT", "/user/{student_id}/", required=("student_id", "FaceRecognition", "semester"), path_fields=("student_id",), body=(("FaceRecognition", "FaceRecognition"), ("semester", "semester"))),
}

API_COUNT = 61

if len(ENDPOINTS) != API_COUNT:
    raise RuntimeError(f"接口目录必须包含 {API_COUNT} 个接口，实际 {len(ENDPOINTS)}")


class RequestBuilder:
    """按接口目录构造请求；只构造，不发送。"""

    @staticmethod
    def build(
        api_name: str,
        *,
        token: str = "",
        signature: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
        base_url: str = BASE_URL,
        **params: Any,
    ) -> ProtocolRequest:
        try:
            endpoint = ENDPOINTS[api_name]
        except KeyError as error:
            raise ProtocolInputError(f"未知接口：{api_name}") from error

        missing = [name for name in endpoint.required if name not in params]
        if missing:
            raise ProtocolInputError(
                f"{api_name} 缺少必填字段：{', '.join(missing)}"
            )

        path_values: dict[str, str] = {}
        for name in endpoint.path_fields:
            value = params.get(name, 0)
            value = value or 0
            path_values[name] = urllib.parse.quote(_js_string(value), safe="")
        path = endpoint.path.format(**path_values)

        query_items: list[tuple[str, str]] = []
        for wire_name, param_name in endpoint.query_fields:
            value = params[param_name]
            if api_name == "getAppVersion" and (value is None or value == ""):
                continue
            query_items.append((wire_name, _js_string(value)))
        query_items.extend(
            (name, _js_string(value))
            for name, value in endpoint.fixed_query.items()
        )
        if endpoint.query_all:
            query_items.extend(
                (name, _js_string(value))
                for name, value in params.items()
                if value is not None and value != ""
            )
        query = urllib.parse.urlencode(query_items)
        url = (base_url.rstrip("/")) + path + ("?" + query if query else "")

        body: dict[str, Any] | None
        if endpoint.method == "GET":
            body = None
        elif endpoint.body_all:
            body = dict(params)
        else:
            body = dict(endpoint.fixed_body)
            for wire_name, param_name in endpoint.body_fields:
                if api_name == "fitnessdata" and param_name == "bu_con":
                    body[wire_name] = params.get(param_name) or ""
                else:
                    body[wire_name] = params[param_name]

        headers: dict[str, str] = {
            "Authorization": token,
            "Content-Type": "application/json",
        }
        if api_name == "uploadRunList":
            headers["Signature"] = signature or sign_running_record(
                params["start_time"],
                params["is_qualified"],
                params["student"],
                params["distance"],
                params["pace"],
            )
        if extra_headers:
            headers.update(extra_headers)

        return ProtocolRequest(
            api_name=api_name,
            method=endpoint.method,
            url=url,
            headers=headers,
            body=body,
            timeout=endpoint.timeout,
        )


@dataclass(frozen=True)
class LoginParams:
    """账号登录参数 DTO。"""

    student_id: str
    password: str
    cid: str = ""

    @classmethod
    def builder(cls) -> "LoginParamsBuilder":
        return LoginParamsBuilder()

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "password": self.password,
            "cid": self.cid,
        }


class LoginParamsBuilder:
    def __init__(self) -> None:
        self._student_id: str | None = None
        self._password: str | None = None
        self._cid: str = ""

    def student_id(self, value: str) -> "LoginParamsBuilder":
        self._student_id = value
        return self

    def password(self, value: str) -> "LoginParamsBuilder":
        self._password = value
        return self

    def cid(self, value: str) -> "LoginParamsBuilder":
        self._cid = value
        return self

    def build(self) -> LoginParams:
        if not self._student_id:
            raise ProtocolInputError("登录参数缺少学号")
        if self._password is None:
            raise ProtocolInputError("登录参数缺少密码")
        return LoginParams(self._student_id, self._password, self._cid)


@dataclass(frozen=True)
class RunRecord:
    """跑步记录 DTO；签名自动按五字段生成，Step_count 对应服务端字段。"""

    running_time: str | None = None
    student: str | None = None
    distance: Any = None
    pace: Any = None
    track: Any = None
    step_count: Any = None
    start_time: Any = None
    end_time: str | None = None
    is_qualified: Any = None
    semester: str | None = None
    submitted_at: str | None = None

    _FIELDS: tuple[str, ...] = (
        "running_time",
        "student",
        "distance",
        "pace",
        "track",
        "step_count",
        "start_time",
        "end_time",
        "is_qualified",
        "semester",
        "submitted_at",
    )

    @classmethod
    def builder(cls) -> "RunRecordBuilder":
        return RunRecordBuilder()

    def signature(self) -> str:
        return sign_running_record(
            self.start_time,
            self.is_qualified,
            self.student,
            self.distance,
            self.pace,
        )

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "running_time": self.running_time,
            "student": self.student,
            "distance": self.distance,
            "pace": self.pace,
            "track": self.track,
            "Step_count": self.step_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "is_qualified": self.is_qualified,
            "semester": self.semester,
            "submitted_at": self.submitted_at,
        }


class RunRecordBuilder:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}

    def _set(self, name: str, value: Any) -> "RunRecordBuilder":
        self._values[name] = value
        return self

    def running_time(self, value: str) -> "RunRecordBuilder":
        return self._set("running_time", value)

    def student(self, value: str) -> "RunRecordBuilder":
        return self._set("student", value)

    def distance(self, value: Any) -> "RunRecordBuilder":
        return self._set("distance", value)

    def pace(self, value: Any) -> "RunRecordBuilder":
        return self._set("pace", value)

    def track(self, value: Any) -> "RunRecordBuilder":
        return self._set("track", value)

    def step_count(self, value: Any) -> "RunRecordBuilder":
        return self._set("step_count", value)

    def start_time(self, value: Any) -> "RunRecordBuilder":
        return self._set("start_time", value)

    def end_time(self, value: str) -> "RunRecordBuilder":
        return self._set("end_time", value)

    def is_qualified(self, value: Any) -> "RunRecordBuilder":
        return self._set("is_qualified", value)

    def semester(self, value: str) -> "RunRecordBuilder":
        return self._set("semester", value)

    def submitted_at(self, value: str) -> "RunRecordBuilder":
        return self._set("submitted_at", value)

    def build(self) -> RunRecord:
        missing = [
            name
            for name in RunRecord._FIELDS
            if name not in self._values or self._values[name] is None
        ]
        if missing:
            raise ProtocolInputError(f"跑步记录缺少字段：{', '.join(missing)}")
        return RunRecord(**self._values)


class JxxyClient:
    """客户端门面：持有会话，聚合全部业务用例方法。"""

    def __init__(
        self,
        token: str = "",
        base_url: str = BASE_URL,
        transport: Transport | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._transport = transport or Transport()

    def build_request(
        self,
        api_name: str,
        *,
        token: str | None = None,
        signature: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
        **params: Any,
    ) -> ProtocolRequest:
        return RequestBuilder.build(
            api_name,
            token=self.token if token is None else token,
            signature=signature,
            extra_headers=extra_headers,
            base_url=self.base_url,
            **params,
        )

    def execute(
        self,
        api_name: str,
        *,
        ssl_context: ssl.SSLContext | None = None,
        **params: Any,
    ) -> ProtocolResponse:
        return self._transport.send(
            self.build_request(api_name, **params),
            ssl_context=ssl_context,
        )

    # ---- 认证 ----

    def login_account(
        self, student_id: str, password: str, cid: str = ""
    ) -> ProtocolResponse:
        dto = LoginParams.builder().student_id(student_id).password(password).cid(cid).build()
        return self.execute("accountLogin", **dto.as_kwargs())

    def login_wechat(self, code: str, cid: str = "") -> ProtocolResponse:
        return self.execute("wxlogin", code=code, cid=cid)

    def change_password(self, student_id: str, password: str) -> ProtocolResponse:
        return self.execute("uppassword", student_id=student_id, password=password)

    def phone_code(self, phone: str) -> ProtocolResponse:
        return self.execute("phonecode", phone=phone)

    def phone_reset(self, phone: str, code: str) -> ProtocolResponse:
        return self.execute("alterphonepasswoed", phone=phone, code=code)

    def cid_validate(self, student_id: str, cid: str) -> ProtocolResponse:
        return self.execute("getcidpasswoed", student_id=student_id, cid=cid)

    def cid_reset(self, student_id: str, cid: str) -> ProtocolResponse:
        return self.execute("altercidpasswoed", student_id=student_id, cid=cid)

    def wechat_bind(self, code: str) -> ProtocolResponse:
        return self.execute("wxopen", code=code)

    def wechat_unbind(self) -> ProtocolResponse:
        return self.execute("wxdelete")

    # ---- 首页 ----

    def token_user(self) -> ProtocolResponse:
        return self.execute("tokenToUser")

    def all_nav(self) -> ProtocolResponse:
        return self.execute("allnavlists")

    def all_informs(self) -> ProtocolResponse:
        return self.execute("allinforms")

    def app_version(self, platform: str, version: str) -> ProtocolResponse:
        return self.execute("getAppVersion", platform=platform, version=version)

    def check_environment(
        self, all_app: str, app_version: str, app_factory: str
    ) -> ProtocolResponse:
        return self.execute(
            "checkenvironment",
            all_app=all_app,
            App_Version=app_version,
            App_factory=app_factory,
        )

    def advertising_lists(self) -> ProtocolResponse:
        return self.execute("getAdvertisingLists")

    def server_time(self) -> ProtocolResponse:
        return self.execute("isServerTimes")

    # ---- 成绩 ----

    def semesters(self) -> ProtocolResponse:
        return self.execute("semesterLists")

    def grades(self, semester: str) -> ProtocolResponse:
        return self.execute("yeargrades", semester=semester)

    def add_point_records(self, page: Any) -> ProtocolResponse:
        return self.execute("getAddPointList", page=page)

    # ---- 校园跑 ----

    def run_records(self, student: str, page: Any) -> ProtocolResponse:
        return self.execute("myrunings", student=student, page=page)

    def run_stats(self, submitted_at: str) -> ProtocolResponse:
        return self.execute("runtendata", time=submitted_at)

    def upload_run(
        self, record: RunRecord | None = None, **kwargs: Any
    ) -> ProtocolResponse:
        dto = record if record is not None else RunRecord(**kwargs)
        return self.execute(
            "uploadRunList",
            signature=dto.signature(),
            **dto.as_kwargs(),
        )

    def run_picture(self, record_id: Any, img_url: str) -> ProtocolResponse:
        return self.execute("uppictures", id=record_id, img_url=img_url)

    def face_verify(self, record_id: Any, url_b: str) -> ProtocolResponse:
        return self.execute("faceverify", id=record_id, UrlB=url_b)

    # ---- 消息 ----

    def system_messages(self, page: Any) -> ProtocolResponse:
        return self.execute("sysMessageList", page=page)

    def mark_message_read(self, message_id: Any) -> ProtocolResponse:
        return self.execute("putskipdata", id=message_id)

    def clear_unread(self) -> ProtocolResponse:
        return self.execute("clearUnreadList")

    def notice_history(self, page: Any) -> ProtocolResponse:
        return self.execute("histnotices", page=page)

    # ---- 活动 ----

    def activities(self, page: Any) -> ProtocolResponse:
        return self.execute("activityInfos", page=page)

    def competitions(self, page: Any) -> ProtocolResponse:
        return self.execute("competitionInfos", page=page)

    # ---- 设置 ----

    def update_phone(self, student_id: str, phone: str) -> ProtocolResponse:
        return self.execute("upphone", student_id=student_id, phone=phone)

    def update_face(
        self, student_id: str, face_url: str, semester: str
    ) -> ProtocolResponse:
        return self.execute(
            "uphumanfacealter",
            student_id=student_id,
            FaceRecognition=face_url,
            semester=semester,
        )
