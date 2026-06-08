from __future__ import annotations
'''
设置页（tabWidget 的 tab4）管理
'''
import logging
import ctypes
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QWidget

from infrastructure.hardware.serial_port_catalog import (
    PortRole,
    SerialPortEntry,
    extract_port_device,
)
from ui.core.utils import get_ui_attr, safe_call, safe_connect
from ui.dialogs.tips_dialog import TipsDialog


class SetPageController:
    """设置页（tabWidget 的 tab4）管理"""

    def __init__(
        self,
        parent: QWidget,
        ui,
        logger: Optional[logging.Logger] = None,
        decoder_port: Optional[str] = None,
        hardware_config_app=None,
        user_app=None,
    ):
        self.parent = parent
        self.ui = ui
        self.logger = logger or logging.getLogger(__name__)
        self.decoder_port = str(decoder_port or "").strip() or None
        self.nes_port = None
        self.nes_port_2 = None
        self.hardware_config_app = hardware_config_app
        self.user_app = user_app
        self._endpoint_volume = None
        self._muted = False
        self._volume_before_mute = None
        self._init_audio_endpoint()

    def bind_signals(self):
        combo = get_ui_attr(self.ui, "comboBox_decoder_port")
        safe_connect(
            self.logger,
            getattr(combo, "currentIndexChanged", None),
            self._on_decoder_port_changed,
        )
        nes_combo = get_ui_attr(self.ui, "comboBox_NES_port")
        safe_connect(
            self.logger,
            getattr(nes_combo, "currentIndexChanged", None),
            self._on_nes_port_changed,
        )
        nes2_combo = get_ui_attr(self.ui, "comboBox_NES_port_2")
        if nes2_combo is not None:
            safe_connect(
                self.logger,
                getattr(nes2_combo, "currentIndexChanged", None),
                self._on_nes_port_2_changed,
            )
        refresh_btn = get_ui_attr(self.ui, "pushButton_refresh_serial_ports")
        safe_connect(
            self.logger,
            getattr(refresh_btn, "clicked", None),
            self._on_refresh_serial_ports,
        )
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if slider is None:
            self.logger.warning("未找到音量滑条: horizontalSlider_volume")
        safe_connect(self.logger, getattr(slider, "valueChanged", None), self._on_volume_changed)
        btn_minus = get_ui_attr(self.ui, "pushButton_vol_minus")
        if btn_minus is None:
            self.logger.warning("未找到音量减按钮: pushButton_vol_minus")
        safe_connect(self.logger, getattr(btn_minus, "clicked", None), self._on_volume_minus)
        btn_add = get_ui_attr(self.ui, "pushButton_vol_add")
        if btn_add is None:
            self.logger.warning("未找到音量加按钮: pushButton_vol_add")
        safe_connect(self.logger, getattr(btn_add, "clicked", None), self._on_volume_add)
        btn_toggle = get_ui_attr(self.ui, "pushButton_vol_shutopen")
        if btn_toggle is None:
            self.logger.warning("未找到静音按钮: pushButton_vol_shutopen")
        safe_connect(self.logger, getattr(btn_toggle, "clicked", None), self._on_volume_toggle)
        self._bind_account_controls()

    def init_ui(self):
        self.refresh_serial_ports(auto_connect=True)
        self._init_volume_controls()
        self._init_account_controls()

    def refresh(self):
        self.refresh_serial_ports(auto_connect=False)

    def open_password_change_tab(self) -> None:
        tab_widget_set = get_ui_attr(self.ui, "tabWidget_set")
        safe_call(self.logger, getattr(tab_widget_set, "setCurrentIndex", None), 1)

    def refresh_serial_ports(self, *, auto_connect: bool = False) -> None:
        """刷新串口下拉列表；auto_connect 时按头环/电刺激识别结果自动连接。"""
        if not self.hardware_config_app:
            self.logger.warning("hardware_config_app 未注入，无法刷新串口")
            return

        if auto_connect:
            entries, assignment, _ = self.hardware_config_app.refresh_and_auto_connect()
            if assignment.head_ring:
                self.decoder_port = assignment.head_ring
            else:
                self.decoder_port = self.hardware_config_app.get_decoder_port() or self.decoder_port
            if assignment.stim:
                self.nes_port = assignment.stim
            else:
                self.nes_port = self.hardware_config_app.get_nes_port() or self.nes_port
            self.nes_port_2 = self.hardware_config_app.get_nes_port_2() or self.nes_port_2
        else:
            entries = self.hardware_config_app.list_port_entries()
            self.decoder_port = self.hardware_config_app.get_decoder_port() or self.decoder_port
            self.nes_port = self.hardware_config_app.get_nes_port() or self.nes_port
            self.nes_port_2 = self.hardware_config_app.get_nes_port_2() or self.nes_port_2

        decoder_combo = get_ui_attr(self.ui, "comboBox_decoder_port")
        nes_combo = get_ui_attr(self.ui, "comboBox_NES_port")
        nes2_combo = get_ui_attr(self.ui, "comboBox_NES_port_2")
        self._populate_port_combo(decoder_combo, entries, self.decoder_port, PortRole.HEAD_RING)
        self._populate_port_combo(nes_combo, entries, self.nes_port, PortRole.STIM)
        self._populate_port_combo(nes2_combo, entries, self.nes_port_2, PortRole.STIM)

    def _populate_port_combo(
        self,
        combo: Optional[QComboBox],
        entries: List[SerialPortEntry],
        selected_port: Optional[str],
        prefer_role: PortRole,
    ) -> None:
        if combo is None:
            return
        prev_block = combo.blockSignals(True)
        combo.clear()
        seen: set[str] = set()
        ordered = sorted(
            entries,
            key=lambda e: (
                0 if e.role is prefer_role else 1,
                0 if e.role is not PortRole.UNKNOWN else 1,
                e.device,
            ),
        )
        for entry in ordered:
            if entry.device in seen:
                continue
            seen.add(entry.device)
            combo.addItem(entry.display_label, entry.device)
        selected = str(selected_port or "").strip()
        if selected:
            idx = combo.findData(selected)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.insertItem(0, f"{selected} · 未知设备", selected)
                combo.setCurrentIndex(0)
        combo.blockSignals(prev_block)

    @staticmethod
    def _combo_port_device(combo: Optional[QComboBox]) -> str:
        if combo is None:
            return ""
        data = combo.currentData(Qt.ItemDataRole.UserRole)
        if data:
            return str(data).strip()
        return extract_port_device(combo.currentText())

    def _on_refresh_serial_ports(self) -> None:
        self.refresh_serial_ports(auto_connect=True)

    def _init_volume_controls(self) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        try:
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setSingleStep(5)
            slider.setPageStep(10)
            slider.setTracking(True)
        except Exception:
            pass
        current = self._get_system_volume_percent()
        if current is not None:
            prev = slider.blockSignals(True)
            slider.setValue(current)
            slider.blockSignals(prev)
            self._muted = current == 0
            if not self._muted:
                self._volume_before_mute = current
        else:
            self.logger.warning("未能读取系统音量，滑条保持默认值")
        self._sync_volume_icon()

    def _init_audio_endpoint(self) -> None:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        self._ensure_audio_endpoint()

    def _ensure_audio_endpoint(self) -> bool:
        if self._endpoint_volume is not None:
            return True
        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            device = AudioUtilities.GetSpeakers()
            if hasattr(device, "Activate"):
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            else:
                interface = device._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint_volume = interface.QueryInterface(IAudioEndpointVolume)
            return True
        except Exception as exc:
            self.logger.warning("初始化系统音量接口失败: %s", exc)
            return False

    def _get_system_volume_percent(self) -> int | None:
        try:
            if self._ensure_audio_endpoint():
                scalar = self._endpoint_volume.GetMasterVolumeLevelScalar()
                return int(round(float(scalar) * 100))
        except Exception as exc:
            self.logger.warning("读取系统音量失败: %s", exc)
        try:
            winmm = ctypes.windll.winmm
            vol = ctypes.c_uint()
            res = winmm.waveOutGetVolume(0, ctypes.byref(vol))
            if res != 0:
                return None
            left = vol.value & 0xFFFF
            right = (vol.value >> 16) & 0xFFFF
            avg = (left + right) / 2.0
            return int(round(avg / 0xFFFF * 100))
        except Exception:
            return None

    def _set_system_volume_percent(self, value: int) -> bool:
        try:
            if self._ensure_audio_endpoint():
                pct = max(0, min(100, int(value)))
                self._endpoint_volume.SetMasterVolumeLevelScalar(pct / 100.0, None)
                return True
        except Exception as exc:
            self.logger.warning("设置系统音量(CoreAudio): %s", exc)
        try:
            winmm = ctypes.windll.winmm
            pct = max(0, min(100, int(value)))
            vol = int(pct / 100 * 0xFFFF)
            winmm.waveOutSetVolume(0, vol | (vol << 16))
            return True
        except Exception as exc:
            self.logger.debug("设置系统音量失败: %s", exc)
        return False

    def _on_volume_changed(self, value: int) -> None:
        ok = self._set_system_volume_percent(value)
        if not ok:
            self.logger.warning("设置系统音量失败，目标值: %s", value)
            return
        current = self._get_system_volume_percent()
        if current is not None and abs(current - int(value)) >= 3:
            self.logger.warning("系统音量未同步，目标=%s 实际=%s", value, current)
        self._muted = int(value) == 0
        if not self._muted:
            self._volume_before_mute = int(value)
        self._sync_volume_icon()

    def _set_volume_slider(self, value: int) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        prev = slider.blockSignals(True)
        slider.setValue(value)
        slider.blockSignals(prev)

    def _sync_volume_icon(self) -> None:
        btn = get_ui_attr(self.ui, "pushButton_vol_shutopen")
        if not btn:
            return
        if self._muted:
            btn.setStyleSheet("border-image: url(:/set/pic/set_volumeshut.png);")
        else:
            btn.setStyleSheet("border-image: url(:/set/pic/set_volumeopen.png);")

    def _on_volume_toggle(self) -> None:
        if not self._muted:
            current = self._get_system_volume_percent()
            if current is not None:
                self._volume_before_mute = current
            self._set_system_volume_percent(0)
            self._set_volume_slider(0)
            self._muted = True
        else:
            restore = self._volume_before_mute if self._volume_before_mute is not None else 50
            self._set_system_volume_percent(restore)
            self._set_volume_slider(restore)
            self._muted = False
        self._sync_volume_icon()

    def _on_volume_add(self) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        step = slider.singleStep() or 5
        slider.setValue(min(slider.maximum(), slider.value() + step))

    def _on_volume_minus(self) -> None:
        slider = get_ui_attr(self.ui, "horizontalSlider_volume")
        if not slider:
            return
        step = slider.singleStep() or 5
        slider.setValue(max(slider.minimum(), slider.value() - step))

    def _on_decoder_port_changed(self, _index: int = -1) -> None:
        combo = get_ui_attr(self.ui, "comboBox_decoder_port")
        next_port = self._combo_port_device(combo)
        if not next_port:
            return
        if self.decoder_port == next_port:
            return
        self.decoder_port = next_port
        if self.hardware_config_app:
            ok = self.hardware_config_app.set_decoder_port(next_port)
            if not ok:
                self.logger.warning("切换解码器端口失败: %s", next_port)

    def _bind_account_controls(self) -> None:
        save_btn = get_ui_attr(self.ui, "pushButton_resetpwdcomfirm")
        cancel_btn = get_ui_attr(self.ui, "pushButton_set_cancel")
        safe_connect(self.logger, getattr(save_btn, "clicked", None), self._on_account_save)
        safe_connect(self.logger, getattr(cancel_btn, "clicked", None), self._on_account_cancel)

    def _init_account_controls(self) -> None:
        for name in (
            "lineEdit_resetpwd",
            "lineEdit_set_oldpwd",
            "lineEdit_set_newpwd",
            "lineEdit_set_confirmpwd",
        ):
            field = get_ui_attr(self.ui, name)
            if field is not None:
                safe_call(self.logger, getattr(field, "setEchoMode", None), QLineEdit.EchoMode.Password)

    def _clear_account_fields(self) -> None:
        for name in (
            "lineEdit_resetpwd",
            "lineEdit_set_oldpwd",
            "lineEdit_set_newpwd",
            "lineEdit_set_confirmpwd",
        ):
            field = get_ui_attr(self.ui, name)
            safe_call(self.logger, getattr(field, "clear", None))

    def _account_field_text(self, name: str) -> str:
        field = get_ui_attr(self.ui, name)
        if field is None:
            return ""
        try:
            return field.text().strip()
        except Exception:
            return ""

    def _on_account_cancel(self) -> None:
        self._clear_account_fields()

    def _on_account_save(self) -> None:
        if not self.user_app:
            TipsDialog.show_tips(self.parent, "用户服务未就绪，无法修改密码")
            return

        admin_password = self._account_field_text("lineEdit_resetpwd")
        old_password = self._account_field_text("lineEdit_set_oldpwd")
        new_password = self._account_field_text("lineEdit_set_newpwd")
        confirm_password = self._account_field_text("lineEdit_set_confirmpwd")

        if not admin_password:
            TipsDialog.show_tips(self.parent, "请输入管理员密码")
            return
        if not old_password:
            TipsDialog.show_tips(self.parent, "请输入旧密码")
            return
        if not new_password:
            TipsDialog.show_tips(self.parent, "请输入新密码")
            return
        if not confirm_password:
            TipsDialog.show_tips(self.parent, "请确认新密码")
            return

        from service.user.user_login_service import ADMIN_PASSWORD

        if admin_password != ADMIN_PASSWORD:
            TipsDialog.show_tips(self.parent, "管理员密码不正确")
            return

        old_password_error = self.user_app.verify_current_password(old_password)
        if old_password_error:
            TipsDialog.show_tips(self.parent, old_password_error)
            return
        if new_password != confirm_password:
            TipsDialog.show_tips(self.parent, "两次输入的新密码不一致")
            return
        password_error = self.user_app.validate_password(new_password)
        if password_error:
            TipsDialog.show_tips(self.parent, password_error)
            return
        if new_password == old_password:
            TipsDialog.show_tips(self.parent, "新密码不能与旧密码相同")
            return

        result = self.user_app.change_password(admin_password, old_password, new_password)
        if result.get("success"):
            TipsDialog.show_tips(self.parent, str(result.get("message") or "密码修改成功"))
            self._clear_account_fields()
        else:
            TipsDialog.show_tips(self.parent, str(result.get("message") or "密码修改失败"))

    def _on_nes_port_changed(self, _index: int = -1) -> None:
        combo = get_ui_attr(self.ui, "comboBox_NES_port")
        next_port = self._combo_port_device(combo)
        if not next_port:
            return
        if self.nes_port == next_port:
            return
        self.nes_port = next_port
        if self.hardware_config_app:
            ok = self.hardware_config_app.set_nes_port(next_port)
            if not ok:
                self.logger.warning("切换串口失败: %s", next_port)

    def _on_nes_port_2_changed(self, _index: int = -1) -> None:
        combo = get_ui_attr(self.ui, "comboBox_NES_port_2")
        next_port = self._combo_port_device(combo)
        if not next_port:
            return
        if self.nes_port_2 == next_port:
            return
        self.nes_port_2 = next_port
        if self.hardware_config_app:
            ok = self.hardware_config_app.set_nes_port_2(next_port)
            if not ok:
                self.logger.warning("切换右腿 NES 串口失败: %s", next_port)
