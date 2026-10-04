"""八字 provider 的发现与诊断。

可选历法库不是核心接口的隐式依赖。这里集中处理探测，避免业务层在各处
import 第三方包，也避免把"包已安装"误报成"算法已验证"。
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    installed: bool
    verified: bool
    message: str


OPTIONAL_PROVIDERS = (
    ("sxtwl", "sxtwl"),
    ("lunar-rs", "lunar_rs"),
)


def inspect_optional_providers() -> tuple[ProviderStatus, ...]:
    """检查可选 provider 是否可导入，不执行网络操作，也不加载用户凭据。"""
    statuses = []
    for name, module in OPTIONAL_PROVIDERS:
        installed = importlib.util.find_spec(module) is not None
        statuses.append(
            ProviderStatus(
                name=name,
                installed=installed,
                verified=False,
                message=(
                    "已安装，但尚未通过本项目 golden cases 验证。"
                    if installed
                    else "未安装；当前不能进行真实历法计算。"
                ),
            )
        )
    return tuple(statuses)


def provider_diagnostics() -> dict[str, object]:
    """返回适合 CLI/API 展示的 provider 诊断信息。"""
    statuses = inspect_optional_providers()
    return {
        "ok": any(status.installed and status.verified for status in statuses),
        "providers": [
            {
                "name": status.name,
                "installed": status.installed,
                "verified": status.verified,
                "message": status.message,
            }
            for status in statuses
        ],
        "warning": "安装第三方库不等于排盘算法已验证。",
    }
