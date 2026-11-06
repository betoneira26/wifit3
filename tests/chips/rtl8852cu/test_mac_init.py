"""M3 MAC bring-up: enable_bb_rf, sys_init, SCC DLE/HFC, trx_init chain, USB post-init."""
from wifit3.chips.rtl8852cu import mac as mac_mod
from wifit3.chips.rtl8852cu import trx
from wifit3.chips.rtl8852cu.constants import (
    R_AX_DMAC_FUNC_EN, R_AX_DMAC_CLK_EN, R_AX_CK_EN, R_AX_CMAC_FUNC_EN,
    R_AX_WDE_PKTBUF_CFG, R_AX_PLE_PKTBUF_CFG, R_AX_WDE_QTA0_CFG, R_AX_PLE_QTA0_CFG,
    R_AX_HCI_FC_CTRL_V1, R_AX_CH_PAGE_CTRL_V1, R_AX_ACH0_PAGE_CTRL_V1,
    R_AX_WDE_INI_STATUS, R_AX_PLE_INI_STATUS, WDE_MGN_INI_RDY, PLE_MGN_INI_RDY,
    R_AX_SS_CTRL, B_AX_SS_INIT_DONE_1, R_AX_ADDR_CAM_CTRL, B_AX_ADDR_CAM_CLR,
    R_AX_DMAC_ERR_IMR, R_AX_CMAC_ERR_IMR, DMAC_ERR_IMR_EN, CMAC0_ERR_IMR_EN,
    R_AX_WDRLS_CFG, RPR_MODE_STF,
    R_AX_USB_ENDPOINT_2_NUMP_V1, R_AX_RXDMA_SETTING,
    R_AX_RXAGG_0_V1, R_AX_RXAGG_1_V1, USB2_BULKSIZE, NUMP,
    SCC_USB2_WDE_SIZE, SCC_USB2_PLE_SIZE, SCC_USB3_WDE_SIZE, SCC_USB3_PLE_SIZE,
    B_AX_DLE_WDE_EN, B_AX_DLE_PLE_EN,
    B_AX_MAC_FUNC_EN, B_AX_DMAC_FUNC_EN, B_AX_CMAC_EN, B_AX_HCI_FC_EN,
    B_AX_HCI_FC_CH12_EN,
)


class RegTransport:
    def __init__(self):
        self.regs = {R_AX_DMAC_FUNC_EN: B_AX_MAC_FUNC_EN | B_AX_DMAC_FUNC_EN,
                     R_AX_CMAC_FUNC_EN: B_AX_CMAC_EN}
        self.writes = []
        self.ready = {R_AX_WDE_INI_STATUS: WDE_MGN_INI_RDY,
                      R_AX_PLE_INI_STATUS: PLE_MGN_INI_RDY,
                      R_AX_SS_CTRL: B_AX_SS_INIT_DONE_1}
        self.open_busy = {R_AX_ADDR_CAM_CTRL: B_AX_ADDR_CAM_CLR}

    def read8(self, a):
        return self.regs.get(a, 0) & 0xFF

    def write8(self, a, v):
        self.regs[a] = v & 0xFF
        self.writes.append((a, v, 8))

    def read16(self, a):
        return self.regs.get(a, 0) & 0xFFFF

    def write16(self, a, v):
        self.regs[a] = v & 0xFFFF
        self.writes.append((a, v, 16))

    def write16_mask(self, a, mask, data):
        shift = (mask & -mask).bit_length() - 1
        self.write16(a, (self.read16(a) & ~mask) | ((data << shift) & mask))

    def write16_clr(self, a, bits):
        self.write16(a, self.read16(a) & ~bits)

    def read32(self, a):
        if a in self.ready:
            return self.ready[a]
        return self.regs.get(a, 0)

    def read32_mask(self, a, mask):
        return self.read32(a) & mask

    def read8_mask(self, a, mask):
        return self.read8(a) & mask

    def write32(self, a, v):
        self.regs[a] = v & 0xFFFFFFFF
        self.writes.append((a, v, 32))
        if a in self.open_busy:
            self.regs[a] &= ~self.open_busy[a]

    def write8_set(self, a, bits):
        self.write8(a, self.read8(a) | bits)

    def write8_clr(self, a, bits):
        self.write8(a, self.read8(a) & ~bits)

    def write8_mask(self, a, mask, data):
        shift = (mask & -mask).bit_length() - 1
        self.write8(a, (self.read8(a) & ~mask) | ((data << shift) & mask))

    def write32_set(self, a, bits):
        self.write32(a, self.read32(a) | bits)

    def write32_clr(self, a, bits):
        self.write32(a, self.read32(a) & ~bits & 0xFFFFFFFF)

    def write32_mask(self, a, mask, data):
        shift = (mask & -mask).bit_length() - 1
        self.write32(a, (self.read32(a) & ~mask) | ((data << shift) & mask))

    def write_xtal_si(self, *_a):
        pass


class _Dev:
    """Stand-in for usb.core.Device: only the speed the DLE row selection reads."""

    def __init__(self, speed):
        self.speed = speed


def test_sys_init_enables_dmac_and_cmac_blocks():
    t = RegTransport()
    mac_mod.RTL8852CUMac(t).sys_init()
    v = t.regs[R_AX_DMAC_FUNC_EN]
    assert v & B_AX_MAC_FUNC_EN and v & B_AX_DMAC_FUNC_EN
    assert v & (B_AX_DLE_WDE_EN | B_AX_DLE_PLE_EN) == 0     # dle_init owns those
    assert t.regs[R_AX_DMAC_CLK_EN]
    assert t.regs[R_AX_CMAC_FUNC_EN] & B_AX_CMAC_EN
    assert t.regs[R_AX_CK_EN]


def test_dle_scc_programs_page_sizes_and_quotas():
    t = RegTransport()
    trx.dle_init(t, trx.PROFILE_SCC)
    wde_pge = SCC_USB2_WDE_SIZE[0]
    ple_pge, ple_lnk, _ = SCC_USB2_PLE_SIZE
    assert wde_pge == 64 and ple_pge == 128
    assert (t.regs[R_AX_WDE_PKTBUF_CFG] & 0x1FFF0000) >> 16 == SCC_USB2_WDE_SIZE[1]   # free pages
    assert (t.regs[R_AX_PLE_PKTBUF_CFG] >> 16) & 0x3FFF == ple_lnk
    assert t.regs[R_AX_WDE_QTA0_CFG]              # hif quota
    assert t.regs[R_AX_PLE_QTA0_CFG + 4 * 6]      # cma0_dma rx qta


def test_dle_scc_usb3_programs_the_usb3_rows():
    """SuperSpeed links get _dle_mem_usb3, whose SCC row differs from USB2 in every field.
    [SRC] rtw8852c.c:122-128."""
    t = RegTransport()
    t.dev = _Dev(4)
    trx.dle_init(t, trx.PROFILE_SCC)
    assert (t.regs[R_AX_WDE_PKTBUF_CFG] & 0x1FFF0000) >> 16 == SCC_USB3_WDE_SIZE[1]
    assert (t.regs[R_AX_PLE_PKTBUF_CFG] >> 16) & 0x3FFF == SCC_USB3_PLE_SIZE[1]
    assert t.regs[R_AX_WDE_QTA0_CFG] & 0xFFF == 344           # hif, wde_qt16
    assert t.regs[R_AX_PLE_QTA0_CFG + 4 * 6] & 0xFFF == 178   # cma0_dma, ple_qt42


def test_is_usb3_follows_the_transport_speed():
    assert not trx.is_usb3(RegTransport())          # no dev / high speed -> USB2 rows
    t = RegTransport()
    t.dev = _Dev(3)
    assert not trx.is_usb3(t)
    t.dev = _Dev(4)
    assert trx.is_usb3(t)


def test_hfc_scc_mixes_channels_and_enables_both_engines():
    t = RegTransport()
    trx.hfc_init(t, trx.PROFILE_SCC)
    v = t.regs[R_AX_HCI_FC_CTRL_V1]
    assert v & B_AX_HCI_FC_EN and v & B_AX_HCI_FC_CH12_EN
    assert t.regs[R_AX_CH_PAGE_CTRL_V1]
    for ch in (0, 1, 2):
        assert R_AX_ACH0_PAGE_CTRL_V1 + ch * 4 in t.regs


def test_trx_init_runs_the_chain_and_enables_imr():
    t = RegTransport()
    trx.trx_init(t)
    assert t.regs[R_AX_DMAC_ERR_IMR] == DMAC_ERR_IMR_EN
    assert t.regs[R_AX_CMAC_ERR_IMR] == CMAC0_ERR_IMR_EN
    assert t.regs[R_AX_WDRLS_CFG] & 0x3 == RPR_MODE_STF


def test_trx_init_selects_the_scc_row_set_from_the_transport():
    """The whole chain (not just dle_init) must land on the USB3 SCC rows on a SuperSpeed link."""
    t = RegTransport()
    t.dev = _Dev(4)
    trx.trx_init(t)
    assert (t.regs[R_AX_PLE_PKTBUF_CFG] >> 16) & 0x3FFF == SCC_USB3_PLE_SIZE[1]
    assert t.regs[R_AX_PLE_QTA0_CFG + 4 * 6] & 0xFFF == 178

    usb2 = RegTransport()
    trx.trx_init(usb2)
    assert (usb2.regs[R_AX_PLE_PKTBUF_CFG] >> 16) & 0x3FFF == SCC_USB2_PLE_SIZE[1]


def test_mac_post_init_sets_bulk_size_and_rxagg():
    t = RegTransport()
    mac_mod.RTL8852CUMac(t).mac_post_init()
    assert t.regs[R_AX_RXDMA_SETTING] == USB2_BULKSIZE
    assert t.regs[R_AX_RXAGG_0_V1] & 0x000000FF == 20
    assert t.regs[R_AX_RXAGG_1_V1] == 0x1F
    # every endpoint 5..12 except 8 saw an IDX write followed by NUMP=1
    ep_writes = [v for (a, v, _w) in t.writes if a == R_AX_USB_ENDPOINT_2_NUMP_V1]
    assert ep_writes == [NUMP] * 7


def test_config_monitor_programs_promiscuous_and_fwd():
    from wifit3.chips.rtl8852cu.constants import (
        R_AX_CTRL_FLTR, R_AX_MGNT_FLTR, R_AX_DATA_FLTR, RX_FLTR_FRAME_TO_HOST,
        R_AX_RX_FLTR_OPT, R_AX_RCR, B_AX_CH_EN_MASK,
        R_AX_PPDU_STAT, R_AX_HW_RPT_FWD
    )
    t = RegTransport()
    mac_mod.RTL8852CUMac(t).config_monitor()
    assert t.regs[R_AX_CTRL_FLTR] == RX_FLTR_FRAME_TO_HOST
    assert t.regs[R_AX_MGNT_FLTR] == RX_FLTR_FRAME_TO_HOST
    assert t.regs[R_AX_DATA_FLTR] == RX_FLTR_FRAME_TO_HOST
    assert t.regs[R_AX_RX_FLTR_OPT] & 0x1 == 1  # B_AX_SNIFFER_MODE
    assert t.regs[R_AX_RCR] & B_AX_CH_EN_MASK == 1
    assert t.regs[R_AX_PPDU_STAT] == 0x2B
    assert t.regs[R_AX_HW_RPT_FWD] & 0x3 == 1


def test_poll_times_out_when_manager_never_ready():
    t = RegTransport()
    t.ready.clear()
    t.ready[R_AX_WDE_INI_STATUS] = 0
    t.ready[R_AX_PLE_INI_STATUS] = 0
    import pytest
    from wifit3.errors import BringUpError
    with pytest.raises(BringUpError):
        trx.dle_init(t, trx.PROFILE_SCC)
