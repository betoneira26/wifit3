"""RTL8852CU USB register-access transport, ported from the mainline rtw89 usb.c.

Every register op is a vendor control transfer on endpoint 0 (rtw89_usb_vendorreq). A read of
a CMAC-window register can come back R32_DEAD until its clock is on, so read_cmac re-enables
the clock and re-reads. This is the layer every later op sits on.
"""
import struct
from typing import Optional

import usb.core

from .constants import (
    RTW89_USB_VENQT, RTW89_USB_VENQT_READ, RTW89_USB_VENQT_WRITE,
    RTW89_USB_VENDORREQ_ATTEMPTS, RTW89_USB_VENDORREQ_TIMEOUT_MS,
    R_AX_CMAC_REG_START, R_AX_CMAC_REG_END, RTW89_R32_DEAD, MAC_REG_POOL_COUNT,
    R_AX_CK_EN, B_AX_CMAC_ALLCKEN,
    R_BE_WLAN_XTAL_SI_CTRL, B_BE_WL_XTAL_SI_CMD_POLL, B_BE_WL_XTAL_SI_CHIPID_MASK,
    B_BE_WL_XTAL_SI_MODE_MASK, B_BE_WL_XTAL_SI_BITMASK_MASK, B_BE_WL_XTAL_SI_DATA_MASK,
    B_BE_WL_XTAL_SI_ADDR_MASK, XTAL_SI_NORMAL_WRITE, XTAL_SI_NORMAL_READ,
)


def _access_cmac(addr: int) -> bool:
    """True for the CMAC register window. [SRC] mac.h:586 ACCESS_CMAC."""
    return R_AX_CMAC_REG_START <= addr <= R_AX_CMAC_REG_END


def _bits(mask: int) -> int:
    """u32_encode_bits shift: mask's trailing-zero count."""
    return (mask & -mask).bit_length() - 1


def _get_bits(val: int, mask: int) -> int:
    return (val & mask) >> _bits(mask)


def _encode_bits(val: int, mask: int) -> int:
    return (val << _bits(mask)) & mask


class RfkWait:
    """Cross-thread wait for a firmware RFK-report C2H, the userland analog of
    rtw89_phy_rfk_report_wait (phy.c). The tuner arms it (`prep`) before an RFK offload H2C
    and blocks on `wait`; the RX reader thread parses the pkt_type=10 report and calls `signal`.
    [SRC] core.c rtw89_wait_for_cond, phy.c report_prep."""

    def __init__(self) -> None:
        self._event = __import__("threading").Event()
        self.enabled = False
        self.armed = False
        self.state: Optional[int] = None       # enum rtw89_rfk_report_state; 1 == OK

    def prep(self) -> None:
        self.state = None
        self._event.clear()
        self.armed = True

    def signal(self, state: int) -> None:
        self.state = state
        self.armed = False
        self._event.set()

    def wait(self, timeout_s: float) -> Optional[int]:
        got = self._event.wait(timeout_s)
        self.armed = False
        return self.state if got else None


class RTL8852CUTransport:
    """Vendor-control register access for the rtw89 8852C over USB."""

    def __init__(self, dev: usb.core.Device):
        self.dev = dev
        self.rfk_wait = RfkWait()   # firmware RFK-report completion, signalled from the RX reader
        self.h2c_counter = 0        # fw_info h2c/c2h register-mailbox counters. [SRC] fw.c
        self.c2h_counter = 0
        self.h2c_seq = 0            # fw_info.h2c_seq: fwcmd sequence number. [SRC] fw.c
        self.cmac_pwr = {0: False}  # RTW89_FLAG_CMAC0_PWR. [SRC] mac.c power_switch
        self.unplugged = False      # RTW89_FLAG_UNPLUGGED: set after 4 continual I/O errors

    def _vendorreq(self, addr: int, data: bytes, length: int, reqtype: int) -> bytes:
        """rtw89_usb_vendorreq: one endpoint-0 vendor control transfer, retried up to 10
        times. [SRC] usb.c:20-73. wValue = addr & 0xFFFF, wIndex = (addr >> 16) & 0xFF."""
        value = addr & 0xFFFF
        index = (addr >> 16) & 0xFF
        for _ in range(RTW89_USB_VENDORREQ_ATTEMPTS):
            try:
                if reqtype == RTW89_USB_VENQT_READ:
                    res = self.dev.ctrl_transfer(reqtype, RTW89_USB_VENQT, value, index,
                                                 length, RTW89_USB_VENDORREQ_TIMEOUT_MS)
                    if len(res) == length:
                        return bytes(res)
                else:
                    n = self.dev.ctrl_transfer(reqtype, RTW89_USB_VENQT, value, index,
                                               data, RTW89_USB_VENDORREQ_TIMEOUT_MS)
                    if n == length:
                        return b""
            except usb.core.USBError:
                pass
        # The kernel flags RTW89_FLAG_UNPLUGGED after 4 continual I/O errors. [SRC] usb.c:59-72.
        return b""

    def read8(self, addr: int) -> int:
        """rtw89_usb_ops_read8. [SRC] usb.c:113-123."""
        if _access_cmac(addr):
            return self._read_cmac(addr) & 0xFF
        d = self._vendorreq(addr, b"", 1, RTW89_USB_VENQT_READ)
        return d[0] if len(d) >= 1 else 0

    def read16(self, addr: int) -> int:
        """rtw89_usb_ops_read16. [SRC] usb.c:125-135."""
        if _access_cmac(addr):
            return self._read_cmac(addr) & 0xFFFF
        d = self._vendorreq(addr, b"", 2, RTW89_USB_VENQT_READ)
        return struct.unpack("<H", d)[0] if len(d) >= 2 else 0

    def read32(self, addr: int) -> int:
        """rtw89_usb_ops_read32. [SRC] usb.c:137-148."""
        if _access_cmac(addr):
            return self._read_cmac(addr)
        d = self._vendorreq(addr, b"", 4, RTW89_USB_VENQT_READ)
        return struct.unpack("<I", d)[0] if len(d) >= 4 else 0

    def write8(self, addr: int, val: int) -> None:
        """rtw89_usb_ops_write8. [SRC] usb.c:150-155."""
        self._vendorreq(addr, struct.pack("<B", val & 0xFF), 1, RTW89_USB_VENQT_WRITE)

    def write16(self, addr: int, val: int) -> None:
        """rtw89_usb_ops_write16. [SRC] usb.c:157-162."""
        self._vendorreq(addr, struct.pack("<H", val & 0xFFFF), 2, RTW89_USB_VENQT_WRITE)

    def write32(self, addr: int, val: int) -> None:
        """rtw89_usb_ops_write32. [SRC] usb.c:164-169."""
        self._vendorreq(addr, struct.pack("<I", val & 0xFFFFFFFF), 4, RTW89_USB_VENQT_WRITE)

    def write32_set(self, addr: int, bits: int) -> None:
        """rtw89_write32_set: read-modify-write, bits OR'd in. [SRC] core.h."""
        self.write32(addr, self.read32(addr) | bits)

    def write32_clr(self, addr: int, bits: int) -> None:
        """rtw89_write32_clr: read-modify-write, bits masked out. [SRC] core.h."""
        self.write32(addr, self.read32(addr) & ~bits & 0xFFFFFFFF)

    def write16_set(self, addr: int, bits: int) -> None:
        """rtw89_write16_set. [SRC] core.h."""
        self.write16(addr, self.read16(addr) | bits)

    def write16_clr(self, addr: int, bits: int) -> None:
        """rtw89_write16_clr. [SRC] core.h."""
        self.write16(addr, self.read16(addr) & ~bits & 0xFFFF)

    def write8_set(self, addr: int, bits: int) -> None:
        """rtw89_write8_set. [SRC] core.h."""
        self.write8(addr, self.read8(addr) | bits)

    def write8_clr(self, addr: int, bits: int) -> None:
        """rtw89_write8_clr. [SRC] core.h."""
        self.write8(addr, self.read8(addr) & ~bits & 0xFF)

    def read32_mask(self, addr: int, mask: int) -> int:
        """rtw89_read32_mask: read `addr`, return `mask`'s field shifted down. [SRC] core.h."""
        return _get_bits(self.read32(addr), mask)

    def write32_mask(self, addr: int, mask: int, data: int) -> None:
        """rtw89_write32_mask: read-modify-write `mask`'s field to `data`. [SRC] core.h."""
        val = (self.read32(addr) & ~mask & 0xFFFFFFFF) | _encode_bits(data, mask)
        self.write32(addr, val)

    def read16_mask(self, addr: int, mask: int) -> int:
        """rtw89_read16_mask. [SRC] core.h."""
        return _get_bits(self.read16(addr), mask)

    def write16_mask(self, addr: int, mask: int, data: int) -> None:
        """rtw89_write16_mask. [SRC] core.h."""
        val = (self.read16(addr) & ~mask & 0xFFFF) | (_encode_bits(data, mask) & 0xFFFF)
        self.write16(addr, val)

    def write8_mask(self, addr: int, mask: int, data: int) -> None:
        """rtw89_write8_mask. [SRC] core.h."""
        val = (self.read8(addr) & ~mask & 0xFF) | (_encode_bits(data, mask) & 0xFF)
        self.write8(addr, val)

    def bulk_out(self, endpoint: int, data: bytes, timeout_ms: int = 5000) -> None:
        """One bulk-OUT transfer (firmware chunk / H2C / TX frame). rtw89_usb_write_port
        submits a URB to the DMA channel's OUT pipe. [SRC] usb.c:264-289."""
        self.dev.write(endpoint, data, timeout_ms)

    def bulk_in(self, endpoint: int, size: int, timeout_ms: int = 1000) -> bytes:
        """One bulk-IN read (RX buffer). rtw89_usb_read_port: a URB on in_pipe of
        RTW89_USB_RECVBUF_SZ. [SRC] usb.c rtw89_usb_rx_resubmit."""
        return bytes(self.dev.read(endpoint, size, timeout_ms))

    def _read_cmac(self, addr: int) -> int:
        """rtw89_usb_read_cmac: read a CMAC-window register, re-enabling its clock and
        re-reading while it returns R32_DEAD. [SRC] usb.c:76-108."""
        addr32 = addr & ~0x3
        shift = (addr & 0x3) * 8
        count = 0
        while True:
            d = self._vendorreq(addr32, b"", 4, RTW89_USB_VENQT_READ)
            val32 = struct.unpack("<I", d)[0] if len(d) >= 4 else RTW89_R32_DEAD
            if val32 != RTW89_R32_DEAD:
                break
            if count >= MAC_REG_POOL_COUNT:
                val32 = RTW89_R32_DEAD
                break
            self.write32(R_AX_CK_EN, B_AX_CMAC_ALLCKEN)
            count += 1
        return val32 >> shift

    def write_xtal_si(self, offset: int, val: int, mask: int) -> None:
        """rtw89_mac_write_xtal_si_be. [SRC] mac_be.c:413-440."""
        val32 = (_encode_bits(offset, B_BE_WL_XTAL_SI_ADDR_MASK) |
                 _encode_bits(val, B_BE_WL_XTAL_SI_DATA_MASK) |
                 _encode_bits(mask, B_BE_WL_XTAL_SI_BITMASK_MASK) |
                 _encode_bits(XTAL_SI_NORMAL_WRITE, B_BE_WL_XTAL_SI_MODE_MASK) |
                 _encode_bits(0, B_BE_WL_XTAL_SI_CHIPID_MASK) |
                 B_BE_WL_XTAL_SI_CMD_POLL)
        self.write32(R_BE_WLAN_XTAL_SI_CTRL, val32)
        for _ in range(100):  # read_poll_timeout 50us * 1000us budget -> bounded spin. mac_be.c:427
            val32 = self.read32(R_BE_WLAN_XTAL_SI_CTRL)
            if not val32 & B_BE_WL_XTAL_SI_CMD_POLL:
                break
        else:
            return  # xtal si not ready(W); the kernel warns and returns -ETIMEDOUT
        if (self.unplugged or
                _get_bits(val32, B_BE_WL_XTAL_SI_ADDR_MASK) != offset or
                _get_bits(val32, B_BE_WL_XTAL_SI_DATA_MASK) != val):
            return  # the kernel warns; the op is logged-and-continued

    def read_xtal_si(self, offset: int) -> int:
        """rtw89_mac_read_xtal_si_be. [SRC] mac_be.c:444-467."""
        val32 = (_encode_bits(offset, B_BE_WL_XTAL_SI_ADDR_MASK) |
                 _encode_bits(0x0, B_BE_WL_XTAL_SI_DATA_MASK) |
                 _encode_bits(0x0, B_BE_WL_XTAL_SI_BITMASK_MASK) |
                 _encode_bits(XTAL_SI_NORMAL_READ, B_BE_WL_XTAL_SI_MODE_MASK) |
                 _encode_bits(0, B_BE_WL_XTAL_SI_CHIPID_MASK) |
                 B_BE_WL_XTAL_SI_CMD_POLL)
        self.write32(R_BE_WLAN_XTAL_SI_CTRL, val32)
        for _ in range(100):
            val32 = self.read32(R_BE_WLAN_XTAL_SI_CTRL)
            if not val32 & B_BE_WL_XTAL_SI_CMD_POLL:
                break
        else:
            return 0
        return _get_bits(val32, B_BE_WL_XTAL_SI_DATA_MASK)
