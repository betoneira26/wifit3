"""M5 TX power: reference packing, power-unit init, trims, and channel-time wiring."""
from unittest.mock import MagicMock

from wifit3.chips.rtl8852cu import chan, phy


class RegTransport:
    def __init__(self):
        self.regs = {}

    def read32(self, addr):
        return self.regs.get(addr, 0)

    def write32(self, addr, val):
        self.regs[addr] = val & 0xFFFFFFFF

    def write32_mask(self, addr, mask, data):
        shift = (mask & -mask).bit_length() - 1
        cur = self.regs.get(addr, 0)
        self.regs[addr] = (cur & ~mask & 0xFFFFFFFF) | ((data << shift) & mask & 0xFFFFFFFF)


def test_bb_cal_txpwr_ref_zero_offset():
    assert phy.bb_cal_txpwr_ref(0, 0) == 0x2B27000
    assert (phy.bb_cal_txpwr_ref(0, 0) >> 9) & 0x1FF == 312


def test_bb_cal_txpwr_ref_clamps_low_rf_cw():
    val = phy.bb_cal_txpwr_ref(-100, 0)
    assert (val >> 9) & 0x1FF == 15 << 3


def test_set_txpwr_ref_writes_rate_ctrl_and_both_paths():
    t = RegTransport()
    phy.set_txpwr_ref(t, 0)

    assert t.regs[phy.R_AX_PWR_RATE_CTRL] & phy.B_AX_PWR_RATE_CTRL_TSSI_MASK == 0
    for addr in (0x15804, 0x17804, 0x15808, 0x17808):
        assert t.regs[addr] & 0x7FFFFFF == 0x2B27000


def test_init_txpwr_unit_presets_and_tb_offsets():
    t = RegTransport()
    phy.init_txpwr_unit(t)

    assert t.regs[phy.R_AX_PWR_UL_CTRL2] == 0x07763333
    assert t.regs[phy.R_AX_PWR_COEXT_CTRL] == 0x01EBF000
    assert t.regs[phy.R_AX_PWR_UL_CTRL0] == 0x0002F8FF
    assert t.regs[phy.R_AX_PWR_UL_TB_1T] == 0
    assert t.regs[phy.R_AX_PWR_UL_TB_2T] == 0xF4F4F4F4


def test_init_tssi_ctrl_zeroes_range_and_applies_presets():
    t = RegTransport()
    phy.init_tssi_ctrl(t)

    assert t.regs[phy.R_AX_TSSI_CTRL_HEAD] == 0
    assert t.regs[phy.R_AX_TSSI_CTRL_TAIL] == 0
    assert t.regs[0xD93C] == 0x0500D500
    assert t.regs[0xD940] == 0x00000500
    assert t.regs[0xD944] == 0x00000005
    assert t.regs[0xD94C] == 0x00220000
    assert t.regs[0xD950] == 0x00030000
    assert t.regs[0xD938] == 0x00010100


def test_power_trim_writes_thermal_and_pa_bias(monkeypatch):
    calls = []
    monkeypatch.setattr(phy, "write_rf", lambda t, p, a, m, d: calls.append((p, a, m, d)))
    phycap = {
        "pg_thermal_trim": True, "thermal_trim": [0x0D, 0xF2],
        "pg_pa_bias_trim": True, "pa_bias_trim": [0x47, 0x47],
    }
    phy.power_trim(MagicMock(), phycap)

    assert calls == [
        (0, phy.RR_TM2, phy.RR_TM2_OFF, 0xE),
        (1, phy.RR_TM2, phy.RR_TM2_OFF, 0x1),
        (0, phy.RR_BIASA, phy.RR_BIASA_TXG, 0x7),
        (0, phy.RR_BIASA, phy.RR_BIASA_TXA, 0x4),
        (1, phy.RR_BIASA, phy.RR_BIASA_TXG, 0x7),
        (1, phy.RR_BIASA, phy.RR_BIASA_TXA, 0x4),
    ]


def test_power_trim_skips_without_programming(monkeypatch):
    calls = []
    monkeypatch.setattr(phy, "write_rf", lambda *a: calls.append(a))
    phy.power_trim(MagicMock(), {
        "pg_thermal_trim": False, "thermal_trim": [0xFF, 0xFF],
        "pg_pa_bias_trim": False, "pa_bias_trim": [0xFF, 0xFF],
    })
    assert calls == []


def test_init_bb_reg_runs_txpwr_unit(monkeypatch):
    calls = []
    monkeypatch.setattr(phy, "_init_reg", lambda *a, **k: None)
    monkeypatch.setattr(phy, "bb_reset", lambda t: None)
    monkeypatch.setattr(phy, "init_txpwr_unit", lambda t: calls.append(t))
    t = MagicMock()
    phy.init_bb_reg(t, 1)
    assert calls == [t]


def test_set_channel_runs_set_txpwr(monkeypatch):
    calls = []
    monkeypatch.setattr(phy, "set_txpwr", lambda t, *a, **kw: calls.append((t, kw.get("band_is_2g", True))))
    t = MagicMock()
    chan.set_channel(t, 1)
    assert calls == [(t, True)]


def test_set_txpwr_byrate_writes_11_registers_and_offset():
    t = MagicMock()
    phy.set_txpwr_byrate(t, band_is_2g=True)
    for i in range(11):
        t.write32.assert_any_call(0xD2C0 + i * 4, phy._BYR_TABLE_2G[i])
    t.write32_mask.assert_called_with(0xD208, 0xFFFFF, 0)


def test_set_txpwr_limit_writes_20_registers():
    t = MagicMock()
    phy.set_txpwr_limit(t)
    assert t.write32.call_count == 20
    for i in range(20):
        t.write32.assert_any_call(0xD2EC + i * 4, 0x3F3F3F3F)


def test_set_txpwr_limit_ru_writes_12_registers():
    t = MagicMock()
    phy.set_txpwr_limit_ru(t)
    assert t.write32.call_count == 12
    for i in range(12):
        t.write32.assert_any_call(0xD33C + i * 4, 0x3F3F3F3F)


def test_set_txpwr_full_chain_called(monkeypatch):
    calls = []
    monkeypatch.setattr(phy, "set_txpwr_byrate", lambda t, band_is_2g: calls.append("byrate"))
    monkeypatch.setattr(phy, "set_txpwr_limit", lambda t: calls.append("limit"))
    monkeypatch.setattr(phy, "set_txpwr_limit_ru", lambda t: calls.append("limit_ru"))
    monkeypatch.setattr(phy, "set_txpwr_ref", lambda t, ofst: calls.append("ref"))
    t = MagicMock()
    phy.set_txpwr(t, band_is_2g=False)
    assert calls == ["byrate", "limit", "limit_ru", "ref"]
