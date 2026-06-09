"""
提示框对话框：单按钮用 tips_sigle.ui，双按钮（取消+确认）用 tips.ui。
根据场景显示成功或警告图标。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional

from PySide6.QtCore import Qt, QFile, QIODevice
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtUiTools import QUiLoader

from ui.core.dialog_overlay import OverlayDialog
from ui.core.resource_loader import ensure_resources_loaded
from ui.core.utils import get_ui_attr, safe_call, safe_connect

UI_ROOT = Path(__file__).resolve().parents[1]
UI_PATH_SINGLE = UI_ROOT / "tips_sigle.ui"   # 仅「确认」
UI_PATH_QUESTION = UI_ROOT / "tips.ui"       # 「取消」+「确认」

TipsIconKind = Literal["success", "warning"]
_ICON_SUCCESS = ":/set/pic/icon_dialog_chengong.png"
_ICON_WARNING = ":/set/pic/icon_dialog_gantan.png"


class TipsDialog(OverlayDialog):
    """单按钮提示用 tips_sigle.ui，双按钮确认用 tips.ui，无顶栏，pushButton_close 关闭。"""

    def __init__(
        self,
        parent=None,
        message: str = "",
        question: bool = False,
        icon: Optional[TipsIconKind] = None,
    ):
        super().__init__(parent)
        ensure_resources_loaded()
        self._logger = logging.getLogger(__name__)
        ui_path = UI_PATH_QUESTION if question else UI_PATH_SINGLE
        ui_file = QFile(str(ui_path))
        if not ui_file.open(QIODevice.ReadOnly):
            raise FileNotFoundError(f"无法打开 UI 文件: {ui_path}")
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        ui_file.close()
        if self.ui is None:
            raise RuntimeError(f"无法加载 UI 文件: {ui_path}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        close_btn = get_ui_attr(self.ui, "pushButton_close")
        safe_connect(self._logger, getattr(close_btn, "clicked", None), self.reject)
        confirm_btn = get_ui_attr(self.ui, "pushButton_confirm")
        if question:
            cancel_btn = get_ui_attr(self.ui, "pushButton_cancel")
            if cancel_btn is not None:
                safe_connect(self._logger, getattr(cancel_btn, "clicked", None), self.reject)
            safe_connect(self._logger, getattr(confirm_btn, "clicked", None), self.accept)
        else:
            safe_connect(self._logger, getattr(confirm_btn, "clicked", None), self.reject)

        self.set_message(message)
        self.set_icon(self._resolve_icon(icon, message, question))

    @staticmethod
    def _resolve_icon(icon: Optional[TipsIconKind], message: str, question: bool) -> str:
        if icon == "success":
            return _ICON_SUCCESS
        if icon == "warning":
            return _ICON_WARNING
        if question:
            return _ICON_WARNING
        text = str(message or "")
        if "成功" in text and "失败" not in text:
            return _ICON_SUCCESS
        return _ICON_WARNING

    def set_message(self, text: str) -> None:
        msg_label = get_ui_attr(self.ui, "label_message")
        if msg_label is not None:
            msg_label.setText(str(text or ""))

    def set_icon(self, icon_path: str) -> None:
        icon_label = get_ui_attr(self.ui, "label_icon")
        if icon_label is not None:
            safe_call(
                self._logger,
                getattr(icon_label, "setStyleSheet", None),
                f"border-image: url({icon_path});",
            )

    def set_title(self, text: str) -> None:
        title_label = get_ui_attr(self.ui, "label_title")
        if title_label is not None:
            title_label.setText(str(text or "提示"))

    @staticmethod
    def show_tips(
        parent=None,
        message: str = "",
        title: str = "",
        icon: Optional[TipsIconKind] = None,
    ) -> None:
        """显示单按钮提示框（点击确认/关闭后返回）。"""
        d = TipsDialog(parent, message=message, question=False, icon=icon)
        if title:
            d.set_title(title)
        d.exec()

    @staticmethod
    def show_confirm(parent=None, message: str = "") -> bool:
        """显示双按钮确认框（取消+确认），使用 tips.ui。返回 True 表示点击「确认」，False 表示「取消」或关闭。"""
        return TipsDialog.show_choice(parent, message, confirm_text="确认", cancel_text="取消")

    @staticmethod
    def show_choice(
        parent=None,
        message: str = "",
        *,
        confirm_text: str = "确认",
        cancel_text: str = "取消",
        icon: Optional[TipsIconKind] = None,
    ) -> bool:
        """显示可自定义按钮文案的双按钮对话框。返回 True 表示点击确认按钮。"""
        d = TipsDialog(
            parent,
            message=message,
            question=True,
            icon=icon if icon is not None else "warning",
        )
        confirm_btn = get_ui_attr(d.ui, "pushButton_confirm")
        cancel_btn = get_ui_attr(d.ui, "pushButton_cancel")
        if confirm_btn is not None:
            confirm_btn.setText(str(confirm_text or "确认"))
        if cancel_btn is not None:
            cancel_btn.setText(str(cancel_text or "取消"))
        return d.exec() == QDialog.DialogCode.Accepted
