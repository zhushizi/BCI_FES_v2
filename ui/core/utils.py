"""
UI 通用工具函数。
用于降低重复样板代码，保持异常处理与日志风格一致。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


def get_ui_attr(ui: Any, name: str) -> Any:
    """安全获取 UI 子控件，缺失时返回 None。"""
    widget = getattr(ui, name, None)
    if widget is not None:
        return widget
    if isinstance(ui, QWidget):
        return ui.findChild(QWidget, name)
    return None


def safe_call(
    logger: logging.Logger,
    func: Optional[Callable[..., Any]],
    *args: Any,
    **kwargs: Any,
) -> bool:
    """安全调用可执行对象，失败时记录异常。"""
    if func is None:
        return False
    try:
        func(*args, **kwargs)
        return True
    except Exception:
        logger.exception("调用失败: %s", getattr(func, "__name__", "unknown"))
        return False


def set_mouse_transparent(widget: QWidget | None) -> None:
    """让控件不拦截鼠标事件，点击穿透到下层控件。"""
    if widget is not None:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)


def set_overlay_labels_mouse_transparent(ui: Any, label_names: tuple[str, ...] | list[str]) -> None:
    """批量设置叠在按钮上的图标标签为鼠标穿透。"""
    for name in label_names:
        set_mouse_transparent(get_ui_attr(ui, name))


def safe_connect(
    logger: logging.Logger,
    signal: Any,
    slot: Callable[..., Any],
) -> bool:
    """安全连接 Qt 信号。"""
    if signal is None:
        return False
    try:
        signal.connect(slot)
        return True
    except Exception:
        logger.exception("信号连接失败")
        return False
