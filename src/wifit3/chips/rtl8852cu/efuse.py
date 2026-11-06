"""RTL8852CU efuse access (M3): physical dump and the logical map.

Physical access on 8852C is the "DDV" path: power the efuse cut, then read one byte at a time
through R_AX_EFUSE_CTRL (addr in B_AX_EF_ADDR_MASK, data in the low byte, B_AX_EF_RDY polls done).
The logical map is reassembled from the physical dump's block headers. [SRC] efuse.c:100-300,
rtw8852c.c:96 (sizes), reg.h.
"""
import time

from wifit3.errors import BringUpError

from .constants import (
    R_AX_EFUSE_CTRL, B_AX_EF_ADDR_MASK, B_AX_EF_RDY,
    R_AX_SYS_WL_EFUSE_CTRL, B_AX_AUTOLOAD_SUS,
    R_AX_PMC_DBG_CTRL2, B_AX_SYSON_DIS_PMCR_AX_WRMSK,
    R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B14, B_AX_PWC_EV2EF_B15, B_AX_ISO_EB2CORE,
)

# rtw8852c_chip_info. [SRC] rtw8852c.c:96 area (sec_ctrl / physical / logical / dav sizes).
SEC_CTRL_EFUSE_SIZE = 4
PHYSICAL_EFUSE_SIZE = 1216
LOGICAL_EFUSE_SIZE = 2048
DAV_PHY_EFUSE_SIZE = 96
DAV_LOG_EFUSE_SIZE = 16

_EF_RDY_TIMEOUT_US = 1_000_000


def _pwr_cut(t, enable: bool) -> None:
    """rtw89_enable_efuse_pwr_cut_ddv / _disable_efuse_pwr_cut_ddv (non-8852A path).
    [SRC] efuse.c:84-118."""
    if enable:
        t.write8_set(R_AX_PMC_DBG_CTRL2, B_AX_SYSON_DIS_PMCR_AX_WRMSK)
        t.write16_set(R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B14)
        time.sleep(0.001)
        t.write16_set(R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B15)
        t.write16_clr(R_AX_SYS_ISO_CTRL, B_AX_ISO_EB2CORE)
        return
    t.write16_set(R_AX_SYS_ISO_CTRL, B_AX_ISO_EB2CORE)
    t.write16_clr(R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B15)
    time.sleep(0.001)
    t.write16_clr(R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B14)
    t.write8_clr(R_AX_PMC_DBG_CTRL2, B_AX_SYSON_DIS_PMCR_AX_WRMSK)


def read_byte(t, addr: int) -> int:
    """One efuse byte through R_AX_EFUSE_CTRL. Power-cut is managed by the caller. [SRC]
    efuse.c:120-142."""
    ctl = (addr << 16) & B_AX_EF_ADDR_MASK
    t.write32(R_AX_EFUSE_CTRL, ctl & ~B_AX_EF_RDY & 0xFFFFFFFF)
    deadline = time.monotonic() + _EF_RDY_TIMEOUT_US / 1_000_000
    while True:
        val = t.read32(R_AX_EFUSE_CTRL)
        if val & B_AX_EF_RDY:
            return val & 0xFF
        if time.monotonic() >= deadline:
            raise BringUpError("efuse", f"EF_RDY timeout at 0x{addr:03x}")


def dump_physical(t, addr: int = 0, size: int = PHYSICAL_EFUSE_SIZE) -> bytes:
    """rtw89_dump_physical_efuse_map (DDV path). [SRC] efuse.c:218-250."""
    _pwr_cut(t, True)
    try:
        return bytes(read_byte(t, a) for a in range(addr, addr + size))
    finally:
        _pwr_cut(t, False)


def autoload_ok(t) -> bool:
    """rtw89_parse_efuse_map_ax's autoload check. [SRC] efuse.c:294."""
    return bool(t.read16(R_AX_SYS_WL_EFUSE_CTRL) & B_AX_AUTOLOAD_SUS)


def _blk_idx(hdr1: int, hdr2: int) -> int:
    return ((hdr2 & 0xF0) >> 4) | ((hdr1 & 0x0F) << 4)


def logical_map(phy: bytes) -> bytes:
    """rtw89_dump_logical_efuse_map: walk the physical block headers and place each enabled
    word into the logical map. [SRC] efuse.c:255-300."""
    log = bytearray(b"\xff" * LOGICAL_EFUSE_SIZE)
    phy_idx = SEC_CTRL_EFUSE_SIZE
    end = len(phy) - SEC_CTRL_EFUSE_SIZE
    while phy_idx < end:
        hdr1, hdr2 = phy[phy_idx], phy[phy_idx + 1]
        if hdr1 == 0xFF or hdr2 == 0xFF:
            break
        blk = _blk_idx(hdr1, hdr2)
        word_en = hdr2 & 0xF
        phy_idx += 2
        for i in range(4):
            if word_en & (1 << i):
                continue
            log_idx = (blk << 3) + (i << 1)
            if phy_idx + 1 > end - 1 or log_idx + 1 > LOGICAL_EFUSE_SIZE:
                raise BringUpError("efuse", "logical map overflow")
            log[log_idx] = phy[phy_idx]
            log[log_idx + 1] = phy[phy_idx + 1]
            phy_idx += 2
    return bytes(log)


# struct rtw8852c_efuse field offsets (pahole on the shipped rtw89_8852c.ko). The MAC lives in the
# tail union, USB variant (u), 0x88 bytes in. [SRC] rtw8852c.h:13-105, rtw8852c.c:642-673.
OFF_CHANNEL_PLAN = 696
OFF_XTAL_K = 697
OFF_THERM_A = 720
OFF_THERM_B = 721
OFF_RFE_TYPE = 714
OFF_COUNTRY_CODE = 715
OFF_MAC_USB = 1024 + 0x88


def parse(log: bytes) -> dict:
    """The subset of rtw8852c_read_efuse this port needs: MAC, RFE type, country, xtal cap and the
    per-path thermals. Values are raw efuse bytes; 0xFF means unprogrammed. [SRC]
    rtw8852c.c:642-673."""
    mac = log[OFF_MAC_USB:OFF_MAC_USB + 6]
    return {
        "mac_addr": mac,
        "mac_addr_str": ":".join(f"{b:02x}" for b in mac),
        "rfe_type": log[OFF_RFE_TYPE],
        "country_code": tuple(log[OFF_COUNTRY_CODE:OFF_COUNTRY_CODE + 2]),
        "channel_plan": log[OFF_CHANNEL_PLAN],
        "xtal_k": log[OFF_XTAL_K],
        "therm_a": log[OFF_THERM_A],
        "therm_b": log[OFF_THERM_B],
    }
