from __future__ import annotations

from pathlib import Path

# 本机首次登录已处理标记（存在则不再弹出默认密码修改提醒）
FIRST_LOGIN_MARKER_NAME = ".first_login_acknowledged"


def project_root() -> Path:
    """BCI_FES 仓库根目录（与 main.py 所在目录一致）。"""
    return Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    return project_root() / "infrastructure" / "config"


def first_login_marker_path() -> Path:
    return config_dir() / FIRST_LOGIN_MARKER_NAME


def is_first_login_on_machine() -> bool:
    """本机是否尚未完成首次登录后的密码提醒流程。"""
    return not first_login_marker_path().is_file()


def mark_first_login_acknowledged() -> None:
    """记录本机已完成首次登录提醒（仅写一次）。"""
    path = first_login_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("acknowledged\n", encoding="utf-8")


def resolve_config_path(raw: str | None) -> str:
    """
    将配置中的可执行路径解析为绝对路径。
    支持前缀 @runtime/ 与 runtime/（均相对仓库根下的 runtime 目录）。
    其余字符串原样返回（兼容仍为绝对路径的旧配置）。
    """
    s = str(raw or "").strip()
    if not s:
        return ""
    key = s.replace("\\", "/")
    root = project_root()
    if key.startswith("@runtime/"):
        rel = key[len("@runtime/") :]
        return str((root / "runtime" / rel).resolve())
    head, sep, tail = key.partition("/")
    if sep and head.lower() == "runtime":
        return str((root / "runtime" / tail).resolve())
    return s
