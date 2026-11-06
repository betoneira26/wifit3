"""Unit tests for RTL8852CU channel tuning and PHY layer."""
from unittest.mock import MagicMock

from wifit3.chips.rtl8852cu import chan, phy
from wifit3.chips.rtl8852cu.constants import RTW89_BAND_2G, RTW89_BAND_5G, RTW89_BAND_6G


def test_channel_to_freq_and_band():
    assert chan.band_of(1) == RTW89_BAND_2G
    assert chan.band_of(14) == RTW89_BAND_2G
    assert chan.band_of(36) == RTW89_BAND_5G
    assert chan.band_of(149) == RTW89_BAND_5G

    assert chan.channel_to_freq(1, RTW89_BAND_2G) == 2412
    assert chan.channel_to_freq(6, RTW89_BAND_2G) == 2437
    assert chan.channel_to_freq(14, RTW89_BAND_2G) == 2484
    assert chan.channel_to_freq(36, RTW89_BAND_5G) == 5180
    assert chan.channel_to_freq(1, RTW89_BAND_6G) == 5955


def test_make_chan():
    c1 = chan.make_chan(1)
    assert c1["channel"] == 1
    assert c1["band_type"] == RTW89_BAND_2G
    assert c1["freq"] == 2412

    c36 = chan.make_chan(36)
    assert c36["channel"] == 36
    assert c36["band_type"] == RTW89_BAND_5G
    assert c36["freq"] == 5180


def test_sel_headline():
    regs = [
        (0xF0000000 | (1 << 16) | 1, 0),  # headline 0: rfe=1, cv=1
        (0xF0000000 | (0xFF << 16) | 0xFF, 0),  # headline 1: wildcard
        (0x1000, 0x1234),  # body
    ]
    hs, hidx = phy._sel_headline(regs, rfe=1, cv=1)
    assert hs == 2
    assert hidx == 0

    hs, hidx = phy._sel_headline(regs, rfe=2, cv=1)
    assert hs == 2
    assert hidx == 1  # fell back to wildcard


def test_phy_set_channel():
    t = MagicMock()
    chan.set_channel(t, 1)

    assert t.write8_mask.called
    assert t.write32.called
    assert t.write32_mask.called


def test_bb_cfg_txrx_path():
    t = MagicMock()
    phy.bb_cfg_txrx_path(t)
    assert t.write32_mask.called


def test_phy_set_channel_bandwidth_40_80_160():
    from wifit3.chips.rtl8852cu.constants import R_AX_WMAC_RFMOD, B_AX_WMAC_RFMOD_MASK

    t = MagicMock()
    # Test 40 MHz
    chan.set_channel(t, 36, bandwidth=1)
    t.write8_mask.assert_any_call(R_AX_WMAC_RFMOD, B_AX_WMAC_RFMOD_MASK, 1)

    # Test 80 MHz
    chan.set_channel(t, 36, bandwidth=2)
    t.write8_mask.assert_any_call(R_AX_WMAC_RFMOD, B_AX_WMAC_RFMOD_MASK, 2)

    # Test 160 MHz
    chan.set_channel(t, 36, bandwidth=3)
    t.write8_mask.assert_any_call(R_AX_WMAC_RFMOD, B_AX_WMAC_RFMOD_MASK, 3)


def test_phy_set_channel_6ghz():
    t = MagicMock()
    chan.set_channel(t, 1, band=RTW89_BAND_6G)
    # R_MUIC = 0x40F8 + 0x10000 = 0x140F8
    t.write32_set.assert_any_call(0x140F8, 1)


def test_rfk_dack_calibration():
    from wifit3.chips.rtl8852cu import rfk
    t = MagicMock()
    rfk.dack(t)
    # S0 ADDCK 0x1C0F8
    t.write32_mask.assert_any_call(0x1C0F8, 1, 1)
    t.write32_mask.assert_any_call(0x1C0F8, 1, 0)
    # S1 ADDCK 0x1C1F8
    t.write32_mask.assert_any_call(0x1C1F8, 1, 1)
    t.write32_mask.assert_any_call(0x1C1F8, 1, 0)


def test_rfk_iqk_and_dpk_offload(mocker):
    from wifit3.chips.rtl8852cu import rfk, firmware
    t = MagicMock()
    spy_h2c = mocker.spy(firmware, "h2c_command")

    rfk.iqk(t, h2c_ep=2, band=0, bw=0, ch=1, cv=1)
    assert spy_h2c.call_count == 1
    assert spy_h2c.call_args.args[4] == 1  # H2C_FUNC_RFK_IQK_OFFLOAD

    rfk.dpk(t, h2c_ep=2, band=0, bw=0, ch=1)
    assert spy_h2c.call_count == 2
    assert spy_h2c.call_args.args[4] == 3  # H2C_FUNC_RFK_DPK_OFFLOAD
