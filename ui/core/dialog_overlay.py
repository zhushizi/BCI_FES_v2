"""
弹窗背景蒙版：#4C4C4C，50% 透明度（rgba(76, 76, 76, 128)）。
"""

from __future__ import annotations

from typing import Callable, TypeVar

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtPrintSupport import QPrintDialog
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QWidget

OVERLAY_STYLE = "background-color: rgba(76, 76, 76, 128);"
OVERLAY_COLOR = QColor(76, 76, 76, 128)

_T = TypeVar("_T")


def resolve_overlay_host(widget: QWidget | None) -> QWidget | None:
    """解析蒙版承载窗口（顶层主窗口）。"""
    if widget is None:
        return None
    win = widget.window()
    if win is not None:
        return win
    return widget


class DialogOverlayWidget(QWidget):
    """蒙版层：作为 host 子控件铺满窗口，置于主界面 UI 之上、模态弹窗之下。"""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self.setObjectName("dialogOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(OVERLAY_STYLE)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), OVERLAY_COLOR)
        self.setPalette(palette)
        self.hide()

    def sync_geometry(self) -> None:
        host = self._host
        if host is None:
            return
        self.setGeometry(0, 0, host.width(), host.height())

    def raise_above_content(self) -> None:
        host = self._host
        if host is None:
            return
        for child in host.children():
            if child is self or not isinstance(child, QWidget):
                continue
            child.lower()
        self.raise_()


class _HostResizeFilter(QObject):
    def __init__(self, overlay: DialogOverlayWidget) -> None:
        super().__init__()
        self._overlay = overlay

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._overlay.sync_geometry()
        return False


class DialogOverlayController:
    def __init__(self, host: QWidget) -> None:
        self._host = host
        self._overlay = DialogOverlayWidget(host)
        self._filter = _HostResizeFilter(self._overlay)
        self._depth = 0

    def push(self) -> None:
        if self._depth == 0:
            self._overlay.sync_geometry()
            self._host.installEventFilter(self._filter)
            self._overlay.raise_above_content()
            self._overlay.show()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        self._depth += 1

    def pop(self) -> None:
        if self._depth <= 0:
            return
        self._depth -= 1
        if self._depth == 0:
            self._overlay.hide()
            self._host.removeEventFilter(self._filter)


def overlay_controller_for(widget: QWidget | None) -> DialogOverlayController | None:
    host = resolve_overlay_host(widget)
    if host is None:
        return None
    attr = "_dialog_overlay_controller"
    ctrl = getattr(host, attr, None)
    if ctrl is None:
        ctrl = DialogOverlayController(host)
        setattr(host, attr, ctrl)
    return ctrl


def run_with_overlay(parent: QWidget | None, func: Callable[[], _T]) -> _T:
    ctrl = overlay_controller_for(parent)
    if ctrl:
        ctrl.push()
    try:
        return func()
    finally:
        if ctrl:
            ctrl.pop()


class OverlayDialog(QDialog):
    """带背景蒙版的对话框基类。"""

    def _overlay_parent(self) -> QWidget | None:
        parent = self.parentWidget()
        if parent is not None:
            return parent
        win = self.window()
        if win is not None and win is not self:
            return win
        return None

    def exec(self) -> int:
        ctrl = overlay_controller_for(self._overlay_parent())
        if ctrl:
            ctrl.push()
        try:
            return super().exec()
        finally:
            if ctrl:
                ctrl.pop()


def message_box_question(
    parent: QWidget | None,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
) -> QMessageBox.StandardButton:
    return run_with_overlay(
        parent,
        lambda: QMessageBox.question(parent, title, text, buttons, default_button),
    )


def get_save_file_name(
    parent: QWidget | None,
    caption: str,
    directory: str = "",
    filter: str = "",
) -> tuple[str, str]:
    return run_with_overlay(
        parent,
        lambda: QFileDialog.getSaveFileName(parent, caption, directory, filter),
    )


def exec_print_dialog(dialog: QPrintDialog) -> int:
    parent = dialog.parent() if isinstance(dialog.parent(), QWidget) else None
    return run_with_overlay(parent, dialog.exec)
