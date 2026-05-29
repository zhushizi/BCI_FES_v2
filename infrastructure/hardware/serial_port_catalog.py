"""
串口枚举与设备角色识别（头环 / 电刺激）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import serial.tools.list_ports


class PortRole(str, Enum):
    HEAD_RING = "head_ring"
    STIM = "stim"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SerialPortEntry:
    device: str
    description: str
    hwid: str
    role: PortRole

    @property
    def display_label(self) -> str:
        if self.role is PortRole.HEAD_RING:
            tag = "头环"
        elif self.role is PortRole.STIM:
            tag = "电刺激设备"
        else:
            tag = "未知设备"
        desc = (self.description or "").strip()
        if desc:
            return f"{self.device} · {tag} ({desc})"
        return f"{self.device} · {tag}"


@dataclass(frozen=True)
class AutoPortAssignment:
    head_ring: Optional[str] = None
    stim: Optional[str] = None


def classify_port(description: str, hwid: str = "") -> PortRole:
    """根据 Windows 串口描述 / HWID 识别设备类型。"""
    desc = description or ""
    blob = f"{desc} {hwid or ''}"
    upper = blob.upper()
    if "CH340" in upper:
        return PortRole.STIM
    if "串行设备" in desc:
        return PortRole.HEAD_RING
    return PortRole.UNKNOWN


def enumerate_serial_ports() -> List[SerialPortEntry]:
    entries: List[SerialPortEntry] = []
    for port in serial.tools.list_ports.comports():
        device = str(port.device or "").strip()
        if not device:
            continue
        description = str(port.description or "")
        hwid = str(port.hwid or "")
        entries.append(
            SerialPortEntry(
                device=device,
                description=description,
                hwid=hwid,
                role=classify_port(description, hwid),
            )
        )
    return entries


def auto_assign_ports(entries: List[SerialPortEntry]) -> AutoPortAssignment:
    head_ring: Optional[str] = None
    stim: Optional[str] = None
    for entry in entries:
        if entry.role is PortRole.HEAD_RING and head_ring is None:
            head_ring = entry.device
        elif entry.role is PortRole.STIM and stim is None:
            stim = entry.device
    return AutoPortAssignment(head_ring=head_ring, stim=stim)


_PORT_DEVICE_RE = re.compile(r"^(COM\d+)", re.IGNORECASE)


def extract_port_device(text: str) -> str:
    """从下拉框展示文本或纯端口号解析 COM 名。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    m = _PORT_DEVICE_RE.match(raw)
    if m:
        return m.group(1).upper()
    if _PORT_DEVICE_RE.fullmatch(raw):
        return raw.upper()
    return raw
