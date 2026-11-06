"""Firmware register mailbox (H2CREG/C2HREG) and PHY-capability setup for the RTL8852CU."""
import pytest

from wifit3.chips.rtl8852cu import firmware
from wifit3.chips.rtl8852cu.constants import (
    R_AX_H2CREG_CTRL_V1, R_AX_C2HREG_CTRL_V1, R_AX_UDM1,
    R_AX_H2CREG_DATA0_V1, R_AX_C2HREG_DATA0_V1,
    B_AX_H2CREG_TRIGGER, B_AX_UDM1_HALMAC_H2C_DEQ_CNT, B_AX_UDM1_HALMAC_C2H_ENQ_CNT,
    RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE, RTW89_FWCMD_C2HREG_FUNC_PHY_CAP,
    RF_B,
)
from wifit3.chips.rtl8852cu.mac import RTL8852CUMac
from wifit3.errors import BringUpError


class FakeTransport:
    """Register file with the mailbox semantics the kernel expects: H2C ctrl reads idle,
    C2H ctrl reads pending, and the C2H data regs hold the queued reply."""

    def __init__(self, c2h_words=(0, 0, 0, 0), c2h_id=RTW89_FWCMD_C2HREG_FUNC_PHY_CAP):
        self.regs = {}
        hdr = (c2h_id & 0x7F) | (1 << 8)          # func + one content word
        self.c2h = [hdr, *c2h_words[1:]]
        self.h2c_counter = 0
        self.c2h_counter = 0

    def read8(self, addr):
        if addr == R_AX_H2CREG_CTRL_V1:
            return 0
        if addr == R_AX_C2HREG_CTRL_V1:
            return 1
        return self.regs.get(addr, 0)

    def write8(self, addr, val):
        self.regs[addr] = val & 0xFF

    def write8_mask(self, addr, mask, data):
        cur = self.regs.get(addr, 0)
        shift = (mask & -mask).bit_length() - 1
        self.regs[addr] = (cur & ~mask & 0xFF) | ((data << shift) & mask & 0xFF)

    def write32(self, addr, val):
        self.regs[addr] = val & 0xFFFFFFFF

    def read32(self, addr):
        if addr == R_AX_C2HREG_DATA0_V1:
            return self.c2h[0]
        if addr == R_AX_C2HREG_DATA0_V1 + 4:
            return self.c2h[1]
        if addr == R_AX_C2HREG_DATA0_V1 + 8:
            return self.c2h[2]
        if addr == R_AX_C2HREG_DATA0_V1 + 12:
            return self.c2h[3]
        return self.regs.get(addr, 0)


def test_write_h2c_reg_packs_id_and_word_count_and_triggers():
    t = FakeTransport()
    firmware.write_h2c_reg(t, RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE, words=[0x12 << 16],
                           content_len=0)
    word0 = t.regs[R_AX_H2CREG_DATA0_V1]
    assert word0 & 0x7F == RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE
    assert (word0 >> 8) & 0xF == 1               # ceil((0 content + 2 hdr) / 4)
    assert (word0 >> 16) & 0xFF == 0x12          # caller-preserved part number
    assert t.regs[R_AX_H2CREG_CTRL_V1] == B_AX_H2CREG_TRIGGER
    assert t.regs[R_AX_UDM1 + 1] & B_AX_UDM1_HALMAC_H2C_DEQ_CNT == 1


def test_read_c2h_reg_decodes_header_and_clears_ctrl():
    t = FakeTransport()
    got = firmware.read_c2h_reg(t)
    assert got["id"] == RTW89_FWCMD_C2HREG_FUNC_PHY_CAP
    assert got["content_len"] == 2               # (1 word << 2) - 2
    assert t.regs[R_AX_C2HREG_CTRL_V1] == 0
    assert t.regs[R_AX_UDM1 + 1] & B_AX_UDM1_HALMAC_C2H_ENQ_CNT == 0x10


def test_setup_phycap_clamps_nss_and_keeps_two_path_antenna_default():
    # w0 rx_nss = 3 (clamped to 2), w1 tx_nss = 2 / prot = 3 (11AX), w3 ant 2/2.
    t = FakeTransport(c2h_words=(3 << 16, 2 | (3 << 8), 0, (2 << 8) | (2 << 16)))
    hal = RTL8852CUMac(t).setup_phycap()
    assert hal["tx_nss"] == 2 and hal["rx_nss"] == 2
    assert hal["protocol"] == 3
    assert hal["no_eht"] is True
    assert hal["antenna_tx"] == 0 and hal["antenna_rx"] == 0
    assert hal["tx_path_diversity"] is False


def test_setup_phycap_single_antenna_selects_rf_b():
    t = FakeTransport(c2h_words=(1 << 16, 1, 0, (1 << 8) | (0 << 16)))
    hal = RTL8852CUMac(t).setup_phycap()
    assert hal["antenna_tx"] == RF_B
    assert hal["antenna_rx"] == 0
    assert hal["tx_nss"] == 1


def test_setup_phycap_rejects_an_unexpected_c2h_id():
    t = FakeTransport(c2h_id=0x0A)
    with pytest.raises(BringUpError) as exc:
        RTL8852CUMac(t).setup_phycap()
    assert exc.value.stage == "phycap"
