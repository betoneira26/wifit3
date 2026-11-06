"""RTL8852CU PHY layer: BB/RF register tables, RF read/write, channel tuning.

Ported from rtw89 mainline: rtw8852c.c, rtw8852c_table.c, rtw8852c_rfk.c, phy.c.
"""
from __future__ import annotations

import struct
import time

from . import firmware
from .assets import bb_tbl, bb_gain_tbl, nctl_tbl, rf_a_tbl, rf_b_tbl
from .constants import (
    RTW89_BAND_2G,
    RTW89_BAND_5G,
    RTW89_BAND_6G,
    B_AX_WMAC_RFMOD_MASK,
    R_AX_WMAC_RFMOD, R_AX_TX_SUB_CARRIER_VALUE, R_AX_TXRATE_CHK,
    B_AX_BAND_MODE, B_AX_RTS_LIMIT_IN_OFDM6, B_AX_CHECK_CCK_EN,
    R_PD_CTRL, B_PD_HIT_DIS, R_SNDCCA_A1, B_SNDCCA_A1_EN,
    R_SNDCCA_A2, B_SNDCCA_A2_VAL,
    R_AX_PWR_RATE_CTRL, B_AX_PWR_RATE_CTRL_TSSI_MASK,
    R_AX_PWR_RATE_OFST_CTRL, R_AX_PWR_BY_RATE, R_AX_PWR_LMT, R_AX_PWR_RU_LMT,
    R_AX_PWR_COEXT_CTRL, R_AX_PWR_UL_CTRL0, R_AX_PWR_UL_CTRL2,
    R_AX_PWR_UL_TB_1T, R_AX_PWR_UL_TB_2T, B_AX_PWR_UL_TB_V1_MASK,
    R_AX_TSSI_CTRL_HEAD, R_AX_TSSI_CTRL_TAIL,
    R_AX_BANDEDGE_CFG, B_AX_BANDEDGE_CFG_IDX_MASK,
    RR_TM2, RR_TM2_OFF, RR_BIASA, RR_BIASA_TXG, RR_BIASA_TXA,
)

CR_BASE_AX = 0x10000
RF_BASE_ADDR_AX = (0xE000, 0xF000)
RF_PATH_A = 0
RF_PATH_B = 1

PHY_HEADLINE_VALID = 0xF
PHY_COND_BRANCH_IF = 0x8
PHY_COND_BRANCH_ELIF = 0x9
PHY_COND_BRANCH_ELSE = 0xA
PHY_COND_BRANCH_END = 0xB
PHY_COND_CHECK = 0x4
PHY_COND_DONT_CARE = 0xFF
BYPASS_CR_DATA = 0xDEADBEEF

RTW89_RF_ADDR_ADSEL_MASK = 0x10000
RFREG_MASK = 0xFFFFF

# SWSI registers
R_SWSI_DATA_V1 = 0x0370
R_SWSI_BIT_MASK_V1 = 0x0374
R_SWSI_READ_ADDR_V1 = 0x0378
R_SWSI_V1 = 0x174C
B_SWSI_W_BUSY_V1 = 1 << 24
B_SWSI_R_BUSY_V1 = 1 << 25
B_SWSI_R_DATA_DONE_V1 = 1 << 26

# BB registers for channel setting
R_UPD_CLK_ADC = 0x0700
B_ENABLE_CCK = 1 << 5
R_PD_ARBITER_OFF = 0x0C80
B_PD_ARBITER_OFF = 1 << 31
R_RXCCA_V1 = 0x2320
B_RXCCA_DIS_V1 = 1 << 0

# RF channel & bandwidth registers
RR_CFGCH = 0x18
RR_CFGCH_V1 = 0x10018
RR_CFGCH_CH = 0xFF                           # GENMASK(7, 0)
RR_CFGCH_BAND0 = 0x300                       # GENMASK(9, 8)
RR_CFGCH_BW = 0xC00                          # GENMASK(11, 10)
RR_CFGCH_BAND1 = 0x30000                     # GENMASK(17, 16)
CFGCH_BW_20M = 3
CFGCH_BW_40M = 2
CFGCH_BW_80M = 1
CFGCH_BW_160M = 0
CFGCH_BAND0_2G = 0
CFGCH_BAND1_2G = 0
CFGCH_BAND0_5G = 1
CFGCH_BAND1_5G = 1
CFGCH_BAND0_6G = 0
CFGCH_BAND1_6G = 3

RR_RSV1 = 0x05
RR_RSV1_RST = 1 << 0
RR_APK = 0x19
RR_APK_MOD = 0x30

RR_LUTWA = 0x33
RR_LUTWA_M2 = 0x1F
RR_LUTWD0 = 0x3F
RR_LUTWD0_LB = 0x3F
RR_RXBB2 = 0x8F
RR_RXBB2_EBW = 0x60
RR_LUTWE2 = 0xEE
RR_LUTWE2_RTXBW = 1 << 2
RR_WLSEL = 0x02
RR_LUTWE = 0xEF

# BTC & Scoreboard registers
R_AX_SCOREBOARD = 0x00AC
R_AX_BTC_CFG = 0xDA00
R_AX_RTK_MODE_CFG_V1 = 0xDA04
R_AX_BT_CNT_CFG = 0xDA10
R_BTC_COEX_WL_REQ = 0xDA24
R_AX_BT_BREAK_TABLE = 0xDA44
R_AX_GNT_SW_CTRL = 0xDA48
R_AX_CCA_CFG_0 = 0xC340
R_AX_BT_PLT = 0xC67C

# H2C commands for RF config
H2C_CAT_OUTSRC = 0x2
H2C_CL_OUTSRC_RF_REG_A = 0x8
H2C_CL_OUTSRC_RF_REG_B = 0x9
RTW89_H2C_RF_PAGE_SIZE = 128
RTW89_H2C_RF_PAGE_NUM = 32

_DELAYS = {0xFE: 0.050, 0xFD: 0.005, 0xFC: 0.001, 0xFB: 50e-6, 0xFA: 5e-6, 0xF9: 1e-6}


_rf_shadow: dict[tuple[int, int], int] = {}


def calc_cfgch_val(central_ch: int, band: int, bw: int = CFGCH_BW_20M) -> int:
    """Calculate the 20-bit composite RR_CFGCH register value."""
    val = (central_ch & 0xFF) | ((bw & 0x3) << 10)
    if band == RTW89_BAND_2G:
        val |= (CFGCH_BAND1_2G << 16) | (CFGCH_BAND0_2G << 8)
    elif band == RTW89_BAND_5G:
        val |= (CFGCH_BAND1_5G << 16) | (CFGCH_BAND0_5G << 8)
    elif band == RTW89_BAND_6G:
        val |= (CFGCH_BAND1_6G << 16) | (CFGCH_BAND0_6G << 8)
    return val


def _config_bb_reg(t, addr: int, data: int) -> None:
    if addr in _DELAYS:
        time.sleep(_DELAYS[addr])
    elif data == BYPASS_CR_DATA:
        return
    else:
        t.write32(addr + CR_BASE_AX, data)


def _check_swsi_busy(t) -> bool:
    val = t.read32(R_SWSI_V1 + CR_BASE_AX)
    return bool(val & (B_SWSI_W_BUSY_V1 | B_SWSI_R_BUSY_V1))


def write_rf(t, rf_path: int, addr: int, mask: int, data: int) -> None:
    """rtw89_phy_write_rf_v1: writes direct or via SWSI. [SRC] phy.c:1245-1260."""
    ad_sel = bool(addr & RTW89_RF_ADDR_ADSEL_MASK)
    # Update shadow
    curr = _rf_shadow.get((rf_path, addr), 0)
    if mask == RFREG_MASK:
        _rf_shadow[(rf_path, addr)] = data & RFREG_MASK
    else:
        _rf_shadow[(rf_path, addr)] = (curr & ~mask) | (data & mask)

    if ad_sel:
        base = RF_BASE_ADDR_AX[rf_path]
        direct = CR_BASE_AX + base + ((addr & 0xFF) << 2)
        t.write32_mask(direct, mask & RFREG_MASK, data)
        time.sleep(0.000001)
        return

    # SWSI indirect path
    for _ in range(50):
        if not _check_swsi_busy(t):
            break
        time.sleep(0.0001)

    data &= RFREG_MASK
    mask &= RFREG_MASK
    b_msk_en = 0
    if mask != RFREG_MASK:
        b_msk_en = 1
        t.write32_mask(R_SWSI_BIT_MASK_V1 + CR_BASE_AX, RFREG_MASK, mask)
        shift = (mask & -mask).bit_length() - 1
        data = (data << shift) & RFREG_MASK

    val = (
        (b_msk_en << 31)
        | ((rf_path & 0x7) << 28)
        | ((addr & 0xFF) << 20)
        | (data & 0xFFFFF)
    )
    t.write32(R_SWSI_DATA_V1 + CR_BASE_AX, val)


def read_rf(t, rf_path: int, addr: int, mask: int = RFREG_MASK) -> int:
    """rtw89_phy_read_rf_v1. [SRC] phy.c:983-1040."""
    ad_sel = bool(addr & RTW89_RF_ADDR_ADSEL_MASK)
    if ad_sel:
        base = RF_BASE_ADDR_AX[rf_path]
        direct = CR_BASE_AX + base + ((addr & 0xFF) << 2)
        val = t.read32_mask(direct, mask)
        return val if isinstance(val, int) else 0

    for _ in range(50):
        if not _check_swsi_busy(t):
            break
        time.sleep(0.0001)

    val = ((rf_path & 0x7) << 8) | (addr & 0xFF)
    t.write32_mask(R_SWSI_READ_ADDR_V1 + CR_BASE_AX, 0x7FF, val)
    time.sleep(0.000002)

    done = False
    swsi = 0
    for _ in range(50):
        val = t.read32(R_SWSI_V1 + CR_BASE_AX)
        if isinstance(val, int) and (val & B_SWSI_R_DATA_DONE_V1):
            swsi = val
            done = True
            break
        time.sleep(0.0001)

    if not done or not isinstance(swsi, int) or (swsi & RFREG_MASK) == 0:
        # Fallback to shadow if SWSI read polling yields 0
        shadow = _rf_shadow.get((rf_path, addr), 0)
        shift = (mask & -mask).bit_length() - 1
        return (shadow & mask) >> shift

    shift = (mask & -mask).bit_length() - 1
    return (swsi & mask) >> shift


def _config_rf_reg(t, rf_path: int, addr: int, data: int, store: list) -> None:
    if addr == 0xFE:
        time.sleep(0.050)
        return
    write_rf(t, rf_path, addr, RFREG_MASK, data)
    if addr < 0x100:
        return
    store.append(((addr << 20) | data) & 0xFFFFFFFF)


def _config_rf_reg_fw(t, h2c_ep: int, rf_path: int, store: list) -> None:
    cls = H2C_CL_OUTSRC_RF_REG_A if rf_path == RF_PATH_A else H2C_CL_OUTSRC_RF_REG_B
    remain = len(store)
    page = 0
    while remain:
        n = min(remain, RTW89_H2C_RF_PAGE_SIZE)
        base = page * RTW89_H2C_RF_PAGE_SIZE
        payload = b"".join(struct.pack("<I", store[base + i]) for i in range(n))
        firmware.h2c_command(t, h2c_ep, H2C_CAT_OUTSRC, cls, page, payload, rack=False, dack=False)
        remain -= n
        page += 1


def _sel_headline(regs: list[tuple[int, int]], rfe: int, cv: int) -> tuple[int, int]:
    """rtw89_phy_sel_headline. [SRC] phy.c:1785-1868."""
    hs = 0
    for a, _ in regs:
        if (a >> 28) != PHY_HEADLINE_VALID:
            break
        hs += 1
    if hs == 0:
        return 0, 0

    compare = ((rfe & 0xFF) << 16) | (cv & 0xFF)
    for i in range(hs):
        target = regs[i][0] & 0x0FFFFFFF
        if target == compare:
            return hs, i

    cv_max = -1
    h_idx = -1
    for i in range(hs):
        target = regs[i][0] & 0x0FFFFFFF
        t_rfe = (target >> 16) & 0xFF
        t_cv = target & 0xFF
        if t_rfe == rfe and cv_max < t_cv <= cv:
            cv_max = t_cv
            h_idx = i
    if h_idx != -1:
        return hs, h_idx

    for i in range(hs):
        target = regs[i][0] & 0x0FFFFFFF
        t_rfe = (target >> 16) & 0xFF
        t_cv = target & 0xFF
        if t_rfe == PHY_COND_DONT_CARE and (t_cv == cv or t_cv == PHY_COND_DONT_CARE):
            return hs, i

    return hs, 0


def _init_reg(regs: list[tuple[int, int]], hs: int, hidx: int, config) -> None:
    """rtw89_phy_init_reg conditional walk. [SRC] phy.c:1896-1936."""
    cfg_target = regs[hidx][0] & 0x0FFFFFFF if hs > 0 else 0
    is_matched = True
    target_found = False
    target = 0
    for i in range(hs, len(regs)):
        a, d = regs[i]
        cond = a >> 28
        if cond in (PHY_COND_BRANCH_IF, PHY_COND_BRANCH_ELIF):
            target = a & 0x0FFFFFFF
        elif cond == PHY_COND_BRANCH_ELSE:
            is_matched = False
            if not target_found:
                return
        elif cond == PHY_COND_BRANCH_END:
            is_matched = True
            target_found = False
        elif cond == PHY_COND_CHECK:
            if target_found:
                is_matched = False
            elif target == cfg_target:
                is_matched = True
                target_found = True
            else:
                is_matched = False
                target_found = False
        elif is_matched:
            config(a, d)


def bb_reset(t) -> None:
    """rtw8852c_bb_reset_all: HW SI reset. [SRC] rtw8852c.c:1659-1682."""
    t.write32_mask(0x11200, 0x70000000, 0x7)
    t.write32_mask(0x13200, 0x70000000, 0x7)
    time.sleep(0.000001)
    t.write32_mask(0x10704, 0x2, 1)
    t.write32_mask(0x10704, 0x2, 0)
    t.write32_mask(0x11200, 0x70000000, 0x0)
    t.write32_mask(0x13200, 0x70000000, 0x0)
    t.write32_mask(0x10704, 0x2, 1)


class BBGainInfo:
    """Baseband gain calibration parameters stored from bb_gain_tbl.
    [SRC] phy.c:1632-1660 rtw89_phy_config_bb_gain_ax."""
    def __init__(self):
        self.lna_gain = [[[0] * 7 for _ in range(2)] for _ in range(7)]
        self.tia_gain = [[[0] * 2 for _ in range(2)] for _ in range(7)]
        self.lna_gain_bypass = [[[0] * 7 for _ in range(2)] for _ in range(7)]
        self.lna_op1db = [[[0] * 7 for _ in range(2)] for _ in range(7)]
        self.tia_lna_op1db = [[[0] * 8 for _ in range(2)] for _ in range(7)]


def _parse_bb_gain(gain: BBGainInfo, addr: int, data: int) -> None:
    """Parse bb_gain_tbl packed union rtw89_phy_bb_gain_arg into BBGainInfo.
    [SRC] phy.c:1450-1660."""
    cfg_type = (addr >> 24) & 0xFF
    gband = (addr >> 16) & 0xFF
    path = (addr >> 8) & 0xFF
    type_ = addr & 0xFF

    if gband >= 7 or path >= 2 or (0xF9 <= addr <= 0xFE):
        return

    if cfg_type == 0:  # gain_error
        if type_ == 0:
            for i in range(4):
                gain.lna_gain[gband][path][i] = data & 0xFF
                data >>= 8
        elif type_ == 1:
            for i in range(4, 7):
                gain.lna_gain[gband][path][i] = data & 0xFF
                data >>= 8
        elif type_ == 2:
            for i in range(2):
                gain.tia_gain[gband][path][i] = data & 0xFF
                data >>= 8
    elif cfg_type == 2:  # bypass
        if type_ == 0:
            for i in range(4):
                gain.lna_gain_bypass[gband][path][i] = data & 0xFF
                data >>= 8
        elif type_ == 1:
            for i in range(4, 7):
                gain.lna_gain_bypass[gband][path][i] = data & 0xFF
                data >>= 8
    elif cfg_type == 3:  # op1db
        if type_ == 0:
            for i in range(4):
                gain.lna_op1db[gband][path][i] = data & 0xFF
                data >>= 8
        elif type_ == 1:
            for i in range(4, 7):
                gain.lna_op1db[gband][path][i] = data & 0xFF
                data >>= 8
        elif type_ == 2:
            for i in range(4):
                gain.tia_lna_op1db[gband][path][i] = data & 0xFF
                data >>= 8
        elif type_ == 3:
            for i in range(4, 8):
                gain.tia_lna_op1db[gband][path][i] = data & 0xFF
                data >>= 8


_TSSI_CTRL_INI = (
    (0xD938, 0x00010100),
    (0xD93C, 0x0500D500),
    (0xD940, 0x00000500),
    (0xD944, 0x00000005),
    (0xD94C, 0x00220000),
    (0xD950, 0x00030000),
)

_TSSI_BANDEDGE_FLAT = (
    (0xD91C, 0xFF000000), (0xD920, 0x000000FF), (0xD920, 0x0000FF00),
    (0xD920, 0x00FF0000), (0xD920, 0xFF000000), (0xD924, 0x000000FF),
    (0xD924, 0x0000FF00), (0xD914, 0xFF000000), (0xD918, 0x000000FF),
    (0xD918, 0x0000FF00), (0xD918, 0x00FF0000), (0xD918, 0xFF000000),
    (0xD91C, 0x000000FF), (0xD91C, 0x0000FF00), (0xD91C, 0x00FF0000),
)

_TSSI_FASTMODE_FLAT = (
    (0xD934, 0x00FF0000), (0xD934, 0xFF000000), (0xD938, 0x000000FF),
    (0xD934, 0x0000FF00),
)


def bb_cal_txpwr_ref(ref: int, pwr_ofst: int) -> int:
    """rtw8852c_bb_cal_txpwr_ref: pack BB/RF CW plus the TSSI reference offset.
    [SRC] rtw8852c.c:2052-2077."""
    pwr_s10_3 = (ref << 1) + (0x27 << 3) - pwr_ofst
    bb_pwr_cw = pwr_s10_3 & 0x7
    rf_pwr_cw = min(max(((pwr_s10_3 & 0xFFFF) >> 3) & 0x3F, 15), 63)
    pwr_cw = (rf_pwr_cw << 3) | bb_pwr_cw
    tssi_ofst_cw = 0x12C + (ref << 1) - (16 << 3) - pwr_ofst
    return (((tssi_ofst_cw << 18) | (pwr_cw << 9) | (ref & 0x1FF))
            & 0xFFFFFFFF)


def set_txpwr_ul_tb_offset(t, pw_ofst: int = 0) -> None:
    """rtw8852c_set_txpwr_ul_tb_offset. [SRC] rtw8852c.c:2078-2113."""
    if pw_ofst < -32 or pw_ofst > 31:
        return
    val_1t = pw_ofst << 2
    val_2t = max(pw_ofst - 3, -32) << 2
    for i in range(4):
        t.write32_mask(R_AX_PWR_UL_TB_1T, B_AX_PWR_UL_TB_V1_MASK << (8 * i), val_1t)
        t.write32_mask(R_AX_PWR_UL_TB_2T, B_AX_PWR_UL_TB_V1_MASK << (8 * i), val_2t)


def init_tssi_ctrl(t) -> None:
    """rtw8852c_init_tssi_ctrl with the flat bandedge. [SRC] rtw8852c.c:2282-2304."""
    for addr in range(R_AX_TSSI_CTRL_HEAD, R_AX_TSSI_CTRL_TAIL + 1, 4):
        t.write32(addr, 0)
    for addr, val in _TSSI_CTRL_INI:
        t.write32(addr, val)
    for addr, mask in _TSSI_BANDEDGE_FLAT:
        t.write32_mask(addr, mask, 0)
    t.write32_mask(R_AX_BANDEDGE_CFG, B_AX_BANDEDGE_CFG_IDX_MASK, 0)
    for addr, mask in _TSSI_FASTMODE_FLAT:
        t.write32_mask(addr, mask, 0)


def init_txpwr_unit(t) -> None:
    """rtw8852c_init_txpwr_unit. [SRC] rtw8852c.c:2305-2325."""
    t.write32(R_AX_PWR_UL_CTRL2, 0x07763333)
    t.write32(R_AX_PWR_COEXT_CTRL, 0x01EBF000)
    t.write32(R_AX_PWR_UL_CTRL0, 0x0002F8FF)
    set_txpwr_ul_tb_offset(t, 0)
    init_tssi_ctrl(t)


def set_txpwr_ref(t, pwr_ofst: int = 0) -> None:
    """rtw8852c_set_txpwr_ref: BB OFDM/CCK reference on both paths.
    [SRC] rtw8852c.c:2114-2149."""
    t.write32_mask(R_AX_PWR_RATE_CTRL, B_AX_PWR_RATE_CTRL_TSSI_MASK, 0)
    ofst_dec = (0 if pwr_ofst > 0 else abs(pwr_ofst),
                pwr_ofst if pwr_ofst > 0 else 0)
    for i, addr in enumerate((0x5800, 0x7800)):
        val = bb_cal_txpwr_ref(0, ofst_dec[i])
        t.write32_mask(addr + 0x4 + CR_BASE_AX, 0x7FFFFFF, val)
    for i, addr in enumerate((0x5800, 0x7800)):
        val = bb_cal_txpwr_ref(0, ofst_dec[i])
        t.write32_mask(addr + 0x8 + CR_BASE_AX, 0x7FFFFFF, val)


_BYR_TABLE_2G = (
    0x28282828, 0x28282828, 0x24262828, 0x28282828, 0x22242628, 0x1A1C1E20,
    0x28282828, 0x28282828, 0x22242628, 0x1A1C1E20, 0x28282828,
)
_BYR_TABLE_5G = (
    0x28282828, 0x24242424, 0x20222424, 0x24242424, 0x1E202224, 0x16181A1C,
    0x24242424, 0x24242424, 0x1E202224, 0x16181A1C, 0x24242424,
)


def set_txpwr_byrate(t, band_is_2g: bool = True) -> None:
    """rtw89_phy_set_txpwr_byrate_ax + rtw89_phy_set_txpwr_offset_ax. [SRC] phy.c:3142-3225."""
    table = _BYR_TABLE_2G if band_is_2g else _BYR_TABLE_5G
    for i, val in enumerate(table):
        t.write32(R_AX_PWR_BY_RATE + i * 4, val)
    t.write32_mask(R_AX_PWR_RATE_OFST_CTRL, 0xFFFFF, 0)


def set_txpwr_limit(t) -> None:
    """rtw89_phy_set_txpwr_limit_ax: 20 dwords uncapped at 0x3F. [SRC] phy.c:3227-3260."""
    for i in range(20):
        t.write32(R_AX_PWR_LMT + i * 4, 0x3F3F3F3F)


def set_txpwr_limit_ru(t) -> None:
    """rtw89_phy_set_txpwr_limit_ru_ax: 12 dwords uncapped at 0x3F. [SRC] phy.c:3262-3295."""
    for i in range(12):
        t.write32(R_AX_PWR_RU_LMT + i * 4, 0x3F3F3F3F)


def set_txpwr(t, band_is_2g: bool = True) -> None:
    """Full per-channel TX power configuration: by-rate, limits, and reference.
    [SRC] rtw8852c.c:2263-2285."""
    set_txpwr_byrate(t, band_is_2g)
    set_txpwr_limit(t)
    set_txpwr_limit_ru(t)
    set_txpwr_ref(t, 0)


def thermal_trim(t, phycap: dict) -> None:
    """rtw8852c_thermal_trim. [SRC] rtw8852c.c:743-770."""
    if not phycap.get("pg_thermal_trim"):
        return
    for path, raw in enumerate(phycap["thermal_trim"][:2]):
        val = ((raw & 0x1) << 3) | ((raw & 0xE) >> 1)
        write_rf(t, path, RR_TM2, RR_TM2_OFF, val)


def pa_bias_trim(t, phycap: dict) -> None:
    """rtw8852c_pa_bias_trim. [SRC] rtw8852c.c:797-825."""
    if not phycap.get("pg_pa_bias_trim"):
        return
    for path, raw in enumerate(phycap["pa_bias_trim"][:2]):
        write_rf(t, path, RR_BIASA, RR_BIASA_TXG, raw & 0xF)
        write_rf(t, path, RR_BIASA, RR_BIASA_TXA, (raw >> 4) & 0xF)


def power_trim(t, phycap: dict) -> None:
    """rtw8852c_power_trim. [SRC] rtw8852c.c:827-830."""
    thermal_trim(t, phycap)
    pa_bias_trim(t, phycap)


def init_bb_reg(t, cv: int) -> None:
    """rtw89_phy_init_bb_reg. [SRC] phy.c:1940-1960."""
    rfe = getattr(t, "rfe_type", 1)
    hs, hidx = _sel_headline(bb_tbl.TABLE, rfe, cv)
    _init_reg(bb_tbl.TABLE, hs, hidx, lambda a, d: _config_bb_reg(t, a, d))

    init_txpwr_unit(t)

    # BB gain table: parse packed metadata into driver memory structure (NOT register writes)
    gain = BBGainInfo()
    hs_g, hidx_g = _sel_headline(bb_gain_tbl.TABLE, rfe, cv)
    _init_reg(bb_gain_tbl.TABLE, hs_g, hidx_g, lambda a, d: _parse_bb_gain(gain, a, d))
    t.bb_gain = gain

    bb_reset(t)


def set_gain_error(t, subband: int, path: int) -> None:
    """rtw8852c_set_gain_error for path A/B. [SRC] rtw8852c.c:1023-1110."""
    gain = getattr(t, "bb_gain", None)
    if not gain:
        return

    # subband to gain_band (rtw89_subband_to_bb_gain_band)
    if subband == 0:
        gain_band = 0
    elif subband == 1:
        gain_band = 1
    elif subband == 3:
        gain_band = 2
    elif subband == 4:
        gain_band = 3
    else:
        gain_band = 0

    is_2g = (subband == 0)

    # LNA registers and masks
    if is_2g:
        lna_regs_p0 = [
            (0x4678, 0x00FF0000), (0x4678, 0xFF000000),
            (0x467C, 0x000000FF), (0x467C, 0x0000FF00), (0x467C, 0x00FF0000), (0x467C, 0xFF000000),
            (0x4680, 0x000000FF)
        ]
        lna_regs_p1 = [
            (0x475C, 0x00FF0000), (0x475C, 0xFF000000),
            (0x4760, 0x000000FF), (0x4760, 0x0000FF00), (0x4760, 0x00FF0000), (0x4760, 0xFF000000),
            (0x4764, 0x000000FF)
        ]
        bypass_regs_p0 = [
            (0x4BB8, 0xFF000000),
            (0x4BBC, 0x000000FF), (0x4BBC, 0x0000FF00), (0x4BBC, 0x00FF0000), (0x4BBC, 0xFF000000),
            (0x4BC0, 0x000000FF), (0x4BC0, 0x0000FF00)
        ]
        bypass_regs_p1 = [
            (0x4C7C, 0xFF000000),
            (0x4C80, 0x000000FF), (0x4C80, 0x0000FF00), (0x4C80, 0x00FF0000), (0x4C80, 0xFF000000),
            (0x4C84, 0x000000FF), (0x4C84, 0x0000FF00)
        ]
        tia_regs_p0 = [(0x4680, 0x00FF0000), (0x4680, 0xFF000000)]
        tia_regs_p1 = [(0x4764, 0x00FF0000), (0x4764, 0xFF000000)]
    else:
        lna_regs_p0 = [
            (0x45DC, 0x00FF0000), (0x45DC, 0xFF000000),
            (0x4660, 0x000000FF), (0x4660, 0x0000FF00), (0x4660, 0x00FF0000), (0x4660, 0xFF000000),
            (0x4664, 0x000000FF)
        ]
        lna_regs_p1 = [
            (0x4740, 0x00FF0000), (0x4740, 0xFF000000),
            (0x4744, 0x000000FF), (0x4744, 0x0000FF00), (0x4744, 0x00FF0000), (0x4744, 0xFF000000),
            (0x4748, 0x000000FF)
        ]
        bypass_regs_p0 = [
            (0x4BB4, 0x000000FF), (0x4BB4, 0x0000FF00), (0x4BB4, 0x00FF0000), (0x4BB4, 0xFF000000),
            (0x4BB8, 0x000000FF), (0x4BB8, 0x0000FF00), (0x4BB8, 0x00FF0000)
        ]
        bypass_regs_p1 = [
            (0x4C78, 0x000000FF), (0x4C78, 0x0000FF00), (0x4C78, 0x00FF0000), (0x4C78, 0xFF000000),
            (0x4C7C, 0x000000FF), (0x4C7C, 0x0000FF00), (0x4C7C, 0x00FF0000)
        ]
        tia_regs_p0 = [(0x4664, 0x00FF0000), (0x4664, 0xFF000000)]
        tia_regs_p1 = [(0x4748, 0x00FF0000), (0x4748, 0xFF000000)]

    lna_list = lna_regs_p0 if path == RF_PATH_A else lna_regs_p1
    bypass_list = bypass_regs_p0 if path == RF_PATH_A else bypass_regs_p1
    tia_list = tia_regs_p0 if path == RF_PATH_A else tia_regs_p1

    for i in range(7):
        reg, mask = lna_list[i]
        val = gain.lna_gain[gain_band][path][i]
        t.write32_mask(reg + CR_BASE_AX, mask, val)

        reg_bp, mask_bp = bypass_list[i]
        val_bp = gain.lna_gain_bypass[gain_band][path][i]
        t.write32_mask(reg_bp + CR_BASE_AX, mask_bp, val_bp)

    for i in range(2):
        reg, mask = tia_list[i]
        val = gain.tia_gain[gain_band][path][i]
        t.write32_mask(reg + CR_BASE_AX, mask, val)


def pmac_stat_reset(t, cck: bool = True) -> None:
    """Reset PMAC statistics and report counters.
    [SRC] phy.c:6035-6055 rtw89_phy_pmac_stat_reset."""
    if cck:
        t.write32_clr(0x2340 + CR_BASE_AX, 1 << 7)
        t.write32_set(0x2340 + CR_BASE_AX, 1 << 7)
    t.write32_set(0x0730 + CR_BASE_AX, 1 << 1)
    t.write32_set(0x0730 + CR_BASE_AX, 1 << 0)
    t.write32_clr(0x0730 + CR_BASE_AX, 1 << 0)


def preinit_rf_nctl_ax(t) -> None:
    """rtw89_phy_preinit_rf_nctl_ax. [SRC] phy.c:2100-2122."""
    t.write32_set(0x10C60, 0x3)
    t.write32_set(0x10C6C, 0x1)
    t.write32_set(0x158AC, 0x8000000)
    t.write32_set(0x178AC, 0x8000000)
    t.write32(0x18000, 0x8)


def init_nctl_reg(t, cv: int) -> None:
    """rtw89_phy_init_rf_nctl. [SRC] phy.c:2100-2135."""
    preinit_rf_nctl_ax(t)
    rfe = getattr(t, "rfe_type", 1)
    hs, hidx = _sel_headline(nctl_tbl.TABLE, rfe, cv)
    _init_reg(nctl_tbl.TABLE, hs, hidx, lambda a, d: _config_bb_reg(t, a, d))


def rf_enable_rx(t) -> None:
    """Set RF Paths A and B to RX mode. [SRC] rtw8852c_rfk.c:4192-4193."""
    for path in (RF_PATH_A, RF_PATH_B):
        write_rf(t, path, 0x05, 1, 1)                   # RR_RSV1, RR_RSV1_RST = 1 (out of reset)
        write_rf(t, path, 0x00, 0xF << 16, 0x3)         # RR_MOD, RR_MOD_MASK = RR_MOD_V_RX (0x3)
        write_rf(t, path, 0x00, 1 << 1, 0)              # RR_MOD, RR_MOD_LO_SEL = 0 (dbcc_en=False)


def init_rf_reg(t, h2c_ep: int, cv: int) -> None:
    """rtw89_phy_init_rf_reg for Radio B and Radio A in kernel table order.
    [SRC] rtw8852c.c:3189, phy.c:2060-2098."""
    rfe = getattr(t, "rfe_type", 1)

    # Radio B (Path B) [SRC] rtw8852c.c:3189 rf_table[0]
    store_b: list[int] = []
    hs_b, hidx_b = _sel_headline(rf_b_tbl.TABLE, rfe, cv)
    _init_reg(rf_b_tbl.TABLE, hs_b, hidx_b, lambda a, d: _config_rf_reg(t, RF_PATH_B, a, d, store_b))
    if h2c_ep is not None:
        _config_rf_reg_fw(t, h2c_ep, RF_PATH_B, store_b)

    # Radio A (Path A) [SRC] rtw8852c.c:3190 rf_table[1]
    store_a: list[int] = []
    hs_a, hidx_a = _sel_headline(rf_a_tbl.TABLE, rfe, cv)
    _init_reg(rf_a_tbl.TABLE, hs_a, hidx_a, lambda a, d: _config_rf_reg(t, RF_PATH_A, a, d, store_a))
    if h2c_ep is not None:
        _config_rf_reg_fw(t, h2c_ep, RF_PATH_A, store_a)

    rf_enable_rx(t)


def _ch_setting(t, path: int, central_ch: int, band: int, is_dav: bool) -> None:
    """rtw8852c _ch_setting. [SRC] rtw8852c_rfk.c:3899-3934."""
    addr = 0x18 if is_dav else 0x10018
    val = read_rf(t, path, addr, RFREG_MASK)
    if not (val & RR_CFGCH_BW):
        val |= (CFGCH_BW_20M << 10)
    val &= ~(RR_CFGCH_BAND1 | RR_CFGCH_BAND0 | RR_CFGCH_CH)
    val |= central_ch & 0xFF
    if band == RTW89_BAND_2G:
        val |= (CFGCH_BAND1_2G << 16) | (CFGCH_BAND0_2G << 8)
    elif band == RTW89_BAND_5G:
        val |= (CFGCH_BAND1_5G << 16) | (CFGCH_BAND0_5G << 8)
    elif band == RTW89_BAND_6G:
        val |= (CFGCH_BAND1_6G << 16) | (CFGCH_BAND0_6G << 8)
    write_rf(t, path, addr, RFREG_MASK, val)
    time.sleep(0.0001)


SCO_BARKER_THRESHOLD = (
    0x1FE4F, 0x1FF5E, 0x2006C, 0x2017B, 0x2028A, 0x20399, 0x204A8, 0x205B6,
    0x206C5, 0x207D4, 0x208E3, 0x209F2, 0x20B00, 0x20D8A,
)

SCO_CCK_THRESHOLD = (
    0x2BDAC, 0x2BF21, 0x2C095, 0x2C209, 0x2C37E, 0x2C4F2, 0x2C666, 0x2C7DB,
    0x2C94F, 0x2CAC3, 0x2CC38, 0x2CDAC, 0x2CF21, 0x2D29E,
)


def bb_cfg_txrx_path(t) -> None:
    """rtw8852c_bb_cfg_txrx_path for 2x2 Path AB. [SRC] rtw8852c.c:2329-2438."""
    rst_mask0 = (1 << 30) | (1 << 31)
    rst_mask1 = (1 << 30) | (1 << 31)
    # Note: write32_mask takes unshifted data.
    t.write32_mask(0x4978 + CR_BASE_AX, 0xF, 3)             # R_CHBW_MOD, B_ANT_RX_SEG0 = 3
    t.write32_mask(0x4974 + CR_BASE_AX, 0x3C000, 3)         # R_FC0_BW, B_ANT_RX_1RCCA_SEG0 = 3
    t.write32_mask(0x4974 + CR_BASE_AX, 0x3C0000, 3)        # R_FC0_BW, B_ANT_RX_1RCCA_SEG1 = 3
    t.write32_mask(0x0D18 + CR_BASE_AX, 0x300, 1)           # R_RXHT_MCS_LIMIT = 1
    t.write32_mask(0x0D18 + CR_BASE_AX, 0x00600000, 1)      # R_RXVHT_MCS_LIMIT = 1 (GENMASK(22, 21))
    t.write32_mask(0x0D80 + CR_BASE_AX, 0x1C000, 1)         # R_RXHE, B_RXHE_MAX_NSS = 1
    t.write32_mask(0x0D80 + CR_BASE_AX, 0xE0000, 1)         # R_RXHE, B_RXHETB_MAX_NSS = 1
    t.write32_mask(0x0D80 + CR_BASE_AX, 0xF0, 8)            # R_RXHE, B_RXHE_USER_MAX = 8 (GENMASK(7, 4))
    t.write32_mask(0x58DC + CR_BASE_AX, rst_mask0, 1)       # R_P0_TXPW_RSTB
    t.write32_mask(0x58DC + CR_BASE_AX, rst_mask0, 3)
    t.write32_mask(0x78DC + CR_BASE_AX, rst_mask1, 1)       # R_P1_TXPW_RSTB
    t.write32_mask(0x78DC + CR_BASE_AX, rst_mask1, 3)


def bb_sethw(t) -> None:
    """rtw8852c_bb_sethw: EVM reporting and front-end GPIO switch init. [SRC] rtw8852c.c:1826-1843."""
    t.write32_set(0x0A10 + CR_BASE_AX, 0x1)  # R_DBCC_80P80_SEL_EVM_RPT, B_DBCC_80P80_SEL_EVM_RPT_EN
    t.write32_set(0x2A10 + CR_BASE_AX, 0x1)  # R_DBCC_80P80_SEL_EVM_RPT2, B_DBCC_80P80_SEL_EVM_RPT2_EN
    bb_gpio_init(t)


def bb_gpio_init(t) -> None:
    """rtw8852c_bb_gpio_init: setup TRSW (Transmit/Receive Switch) and LNA (Low Noise Amplifier)
    for Path A and Path B. [SRC] rtw8852c.c:1769-1814."""
    for base in (0x5800, 0x7800):
        t.write32_set(base + 0x68 + CR_BASE_AX, 1 << 1)     # B_P0_TRSW_A
        t.write32_clr(base + 0x68 + CR_BASE_AX, (1 << 2) | (0x7 << 5)) # B_P0_TRSW_X | B_P0_TRSW_SO_A2
        t.write32(base + 0x80 + CR_BASE_AX, 0x77777777)
        t.write32(base + 0x84 + CR_BASE_AX, 0x77777777)

    t.write32(0x0334 + CR_BASE_AX, 0xFFFFFFFF)              # R_RFE_E_A2
    t.write32(0x0338 + CR_BASE_AX, 0)                       # R_RFE_O_SEL_A2
    t.write32(0x033C + CR_BASE_AX, 0)                       # R_RFE_SEL0_A2
    t.write32(0x0340 + CR_BASE_AX, 0)                       # R_RFE_SEL32_A2

    # TRSW switch table: computed from rtw8852c_bb_gpio_trsw calls (all entries produce 0xA9A90002)
    t.write32(0x5868 + CR_BASE_AX, 0xA9A90002)
    t.write32(0x7868 + CR_BASE_AX, 0xA9A90002)

    # RFM: PAPE_RFM (val=0), TRSW_RFM (val=4), LNAON_RFM (val=8) -> 0x00080400
    t.write32(0x5894 + CR_BASE_AX, 0x00080400)
    t.write32(0x7894 + CR_BASE_AX, 0x00080400)


def ctrl_btg_bt_rx(t, is_2g: bool) -> None:
    """rtw8852c_ctrl_btg_bt_rx: route 2.4G BT/Wi-Fi shared antenna paths.
    [SRC] rtw8852c.c:2648-2690."""
    if is_2g:
        t.write32_mask(0x4738 + CR_BASE_AX, 1 << 19, 1)     # R_PATH0_BT_SHARE_V1
        t.write32_mask(0x4738 + CR_BASE_AX, 1 << 22, 0)     # R_PATH0_BTG_PATH_V1
        t.write32_mask(0x476C + CR_BASE_AX, 0xFF000000, 0x20) # R_PATH1_G_LNA6_OP1DB_V1
        t.write32_mask(0x4778 + CR_BASE_AX, 0xFF, 0x30)     # R_PATH1_G_TIA0_LNA6_OP1DB_V1
        t.write32_mask(0x4AA4 + CR_BASE_AX, 1 << 19, 1)     # R_PATH1_BT_SHARE_V1
        t.write32_mask(0x4AA4 + CR_BASE_AX, 1 << 22, 1)     # R_PATH1_BTG_PATH_V1
        t.write32_mask(0x0980 + CR_BASE_AX, 0x1E0000, 0)    # R_PMAC_GNT, B_PMAC_GNT_P1 = 0
        t.write32_mask(0x4978 + CR_BASE_AX, 1 << 14, 1)     # R_CHBW_MOD, B_BT_SHARE = 1
        t.write32_mask(0x4974 + CR_BASE_AX, 0x3C00000, 2)   # R_FC0_BW, B_ANT_RX_BT_SEG0 = 2
        t.write32_mask(0x441C + CR_BASE_AX, 1 << 31, 1)     # R_BT_DYN_DC_EST_EN
        t.write32_mask(0x0C6C + CR_BASE_AX, 1 << 21, 1)     # R_GNT_BT_WGT_EN
    else:
        t.write32_mask(0x4738 + CR_BASE_AX, 1 << 19, 0)
        t.write32_mask(0x4738 + CR_BASE_AX, 1 << 22, 0)
        t.write32_mask(0x476C + CR_BASE_AX, 0xFF000000, 0x1A)
        t.write32_mask(0x4778 + CR_BASE_AX, 0xFF, 0x2A)
        t.write32_mask(0x4AA4 + CR_BASE_AX, 1 << 19, 0)
        t.write32_mask(0x4AA4 + CR_BASE_AX, 1 << 22, 0)
        t.write32_mask(0x0980 + CR_BASE_AX, 0x1E0000, 0xF)
        t.write32_mask(0x0980 + CR_BASE_AX, 0x3C000000, 0x4)
        t.write32_mask(0x4978 + CR_BASE_AX, 1 << 14, 0)
        t.write32_mask(0x4974 + CR_BASE_AX, 0x3C00000, 0)
        t.write32_mask(0x441C + CR_BASE_AX, 1 << 31, 0)
        t.write32_mask(0x0C6C + CR_BASE_AX, 1 << 21, 0)


def btc_init(t) -> None:
    """Bluetooth Coexistence & Front-End Antenna Routing initialization.
    Grants full, exclusive antenna & RF access to Wi-Fi.
    [SRC] rtw8852c.c:2690-2760, coex.c:5650-5730, 8755-8780, mac.c:6471-6500, 6588-6640."""
    # 1. Update Scoreboard: notify BT firmware that Wi-Fi is active and running (TP major mode)
    # B_AX_TOGGLE (bit 31), byte 3 = 0x81 (MAC_AX_NOTIFY_TP_MAJOR), driver bits = 0x4003 (ACTIVE | ON | BTLOG)
    t.write32(R_AX_SCOREBOARD, 0x81004003)
    time.sleep(0.001)

    # 2. PTA hardware init: RTK mode, 5MHz sampling, enable counter, break table
    t.write32_set(R_AX_BTC_CFG, (1 << 31) | (1 << 16))      # B_AX_BTC_EN | B_AX_BTG_LNA1_GAIN_SEL
    t.write32_mask(R_AX_RTK_MODE_CFG_V1, 0xFF, 5)            # MAC_AX_RTK_RATE = 5
    t.write32_set(R_AX_BT_CNT_CFG, (1 << 0) | (1 << 1))     # EN | RST
    t.write16_set(R_AX_CCA_CFG_0, 1 << 5)                    # B_AX_BTCCA_EN
    t.write16_clr(R_AX_CCA_CFG_0, 1 << 9)                    # B_AX_BTCCA_BRK_TXOP_EN
    t.write32(R_AX_BT_BREAK_TABLE, 0xF0FFFFFF)              # BTC_BREAK_PARAM

    # 3. Wi-Fi Priority over BT: ACK/Response and Beacon
    t.write32_set(R_BTC_COEX_WL_REQ, (1 << 22) | (1 << 10)) # B_BTC_TX_BCN_HI | B_BTC_RSP_ACK_HI

    # 4. RF GNT debug off on Path A and Path B
    write_rf(t, RF_PATH_A, RR_WLSEL, RFREG_MASK, 0)
    write_rf(t, RF_PATH_B, RR_WLSEL, RFREG_MASK, 0)

    # 5. TRX Mask Table: unmask Wi-Fi passthrough on RF paths A and B (SS group 0 and TX group 2)
    def _set_trx_mask(path: int, group: int, val: int) -> None:
        write_rf(t, path, RR_LUTWE, RFREG_MASK, 0x20000)
        write_rf(t, path, RR_LUTWA, RFREG_MASK, group)
        write_rf(t, path, RR_LUTWD0, RFREG_MASK, val)
        write_rf(t, path, RR_LUTWE, RFREG_MASK, 0x00000)

    _set_trx_mask(RF_PATH_A, 0, 0x5FF)                       # BTC_BT_SS_GROUP = 0
    _set_trx_mask(RF_PATH_B, 0, 0x5FF)
    _set_trx_mask(RF_PATH_A, 2, 0x5FF)                       # BTC_BT_TX_GROUP = 2

    # 6. Exclusive Wi-Fi Software Grant (BTC_ANT_WONLY): force GNT_WL on BB, RFC S0, RFC S1, TX, RX
    t.write32(R_AX_GNT_SW_CTRL, 0x003D7DDF)

    # 7. BT PLT: grant WL on MAC 0 TX and RX
    t.write16(R_AX_BT_PLT, 0x11)                             # B_AX_TX_PLT_GNT_WL | B_AX_RX_PLT_GNT_WL


def bb_enable_rx(t, band: int) -> None:
    """Take ADC FIFO, packet detector (PD), RX CCA and baseband out of reset.
    [SRC] rtw8852c.c:1684-1708 (bb_reset_en), 1961-1969 (adc_en), 1953-1959 (dfs_en)."""
    # adc_en(True): release ADC FIFO reset (R_ADC_FIFO = 0x20FC, B_ADC_FIFO_RST = 0xFF000000)
    t.write32_mask(0x20FC + CR_BASE_AX, 0xFF000000, 0x0)
    # dfs_en(True) (R_UPD_P0 = 0x0000, B_UPD_P0_EN = 1 << 31)
    t.write32_mask(0x0000 + CR_BASE_AX, 1 << 31, 1)
    # bb_reset_en(True)
    t.write32_mask(0x1200 + CR_BASE_AX, 0x70000000, 0x0)
    t.write32_mask(0x3200 + CR_BASE_AX, 0x70000000, 0x0)
    t.write32_set(0x0704 + CR_BASE_AX, 0x2)
    # R_RXCCA_V1 (0x2320): B_RXCCA_DIS_V1 (bit 0) = 0 if 2G else 1
    t.write32_mask(R_RXCCA_V1 + CR_BASE_AX, B_RXCCA_DIS_V1, 0 if band == RTW89_BAND_2G else 1)
    # R_PD_ARBITER_OFF (0x0C80): B_PD_ARBITER_OFF (bit 31) = 0 if 2G else 1
    t.write32_mask(R_PD_ARBITER_OFF + CR_BASE_AX, B_PD_ARBITER_OFF, 0 if band == RTW89_BAND_2G else 1)
    # R_PD_CTRL (0x0C3C): B_PD_HIT_DIS (bit 9) = 0 (allow packet detector hits)
    t.write32_mask(R_PD_CTRL + CR_BASE_AX, B_PD_HIT_DIS, 0)


def _bw_setting(t, path: int, bw: int = 0, is_dav: bool = True, central_ch: int = 0, band: int = 0) -> None:
    """rtw8852c _bw_setting for 20/40/80/160MHz. [SRC] rtw8852c_rfk.c:3840-3866."""
    addr = 0x18 if is_dav else 0x10018
    val = read_rf(t, path, addr, RFREG_MASK)
    if not (val & RR_CFGCH_CH) and central_ch:
        val |= central_ch & 0xFF
        if band == RTW89_BAND_2G:
            val |= (CFGCH_BAND1_2G << 16) | (CFGCH_BAND0_2G << 8)
        elif band == RTW89_BAND_5G:
            val |= (CFGCH_BAND1_5G << 16) | (CFGCH_BAND0_5G << 8)
        elif band == RTW89_BAND_6G:
            val |= (CFGCH_BAND1_6G << 16) | (CFGCH_BAND0_6G << 8)
    cfgch_bw = max(0, min(3 - bw, 3))
    val &= ~RR_CFGCH_BW
    val |= (cfgch_bw << 10)

    # Delay and BW selection per bandwidth [SRC] rtw8852c_rfk.c:3840-3860
    if bw == 3:      # 160M
        delay, bw_sel = 1, 0xB
    elif bw == 2:    # 80M
        delay, bw_sel = 2, 0xD
    else:            # 20M / 40M
        delay, bw_sel = 3, 0xF

    t.write32_mask(0xC0D4 + (path << 8) + CR_BASE_AX, 0x0C000000, delay)
    t.write32_mask(0xC0D8 + (path << 8) + CR_BASE_AX, 0x000001E0, bw_sel)
    write_rf(t, path, addr, RFREG_MASK, val)


def _set_rxbb_bw(t, path: int, bw: int = 0) -> None:
    """rtw8852c _set_rxbb_bw for 20/40/80/160MHz. [SRC] rtw8852c_rfk.c:3961-3995."""
    write_rf(t, path, RR_LUTWE2, RR_LUTWE2_RTXBW, 1)
    write_rf(t, path, RR_LUTWA, RR_LUTWA_M2, 0x0A)
    lut_val = (0x03 if bw == 3 else
               0x0B if bw == 2 else
               0x13 if bw == 1 else
               0x1B)
    write_rf(t, path, RR_LUTWD0, RR_LUTWD0_LB, lut_val)
    write_rf(t, path, RR_LUTWE2, RR_LUTWE2_RTXBW, 0)
    # TIA bandwidth
    tia_ebw = 0 if bw == 3 else 2
    write_rf(t, path, RR_RXBB2, RR_RXBB2_EBW, tia_ebw)


def set_channel(t, chan: dict) -> None:
    """rtw8852c_set_channel (MAC + BB + RF) for 20/40/80/160MHz channel tuning."""
    band = chan["band_type"]
    ch = chan["channel"]
    freq = chan["freq"]
    bw = chan.get("band_width", 0)
    pri_ch = chan.get("pri_sb_idx", 0)

    # MAC
    rfmod_val = min(bw, 3)
    t.write8_mask(R_AX_WMAC_RFMOD, B_AX_WMAC_RFMOD_MASK, rfmod_val)
    t.write32(R_AX_TX_SUB_CARRIER_VALUE, 0)
    chk_rate_mask = B_AX_BAND_MODE if band == RTW89_BAND_2G else (B_AX_CHECK_CCK_EN | B_AX_RTS_LIMIT_IN_OFDM6)
    t.write8_clr(R_AX_TXRATE_CHK, B_AX_BAND_MODE | B_AX_CHECK_CCK_EN | B_AX_RTS_LIMIT_IN_OFDM6)
    t.write8_set(R_AX_TXRATE_CHK, chk_rate_mask)

    # BB
    is_2g = band == RTW89_BAND_2G
    is_6g = band == RTW89_BAND_6G
    subband = chan.get("subband_type", 0 if is_2g else 1)
    set_gain_error(t, subband, RF_PATH_A)
    set_gain_error(t, subband, RF_PATH_B)

    if is_2g and 1 <= ch <= 14:
        idx = ch - 1
        t.write32_mask(0x4A1C + CR_BASE_AX, 0x7FFFF, SCO_BARKER_THRESHOLD[idx])
        t.write32_mask(0x4A20 + CR_BASE_AX, 0x7FFFF, SCO_CCK_THRESHOLD[idx])
        # CCK pulse shaping filter coefficients. [SRC] rtw8852c.c:1212-1248
        if ch == 14:
            t.write32_mask(0x45BC + CR_BASE_AX, 0xFFFFFFFF, 0x3b13ff)
            t.write32_mask(0x45CC + CR_BASE_AX, 0xFFFFFFFF, 0x1c42de)
            t.write32_mask(0x45D0 + CR_BASE_AX, 0xFFFFFFFF, 0xfdb0ad)
            t.write32_mask(0x45D4 + CR_BASE_AX, 0xFFFFFFFF, 0xf60f6e)
            t.write32_mask(0x45D8 + CR_BASE_AX, 0xFFFFFFFF, 0xfd8f92)
            t.write32_mask(0x45C0 + CR_BASE_AX, 0xFFFFFFFF, 0x2d011)
            t.write32_mask(0x45C4 + CR_BASE_AX, 0xFFFFFFFF, 0x1c02c)
            t.write32_mask(0x45C8 + CR_BASE_AX, 0xFFFFFFFF, 0xfff00a)
        else:
            t.write32_mask(0x45BC + CR_BASE_AX, 0xFFFFFFFF, 0x3d23ff)
            t.write32_mask(0x45CC + CR_BASE_AX, 0xFFFFFFFF, 0x29b354)
            t.write32_mask(0x45D0 + CR_BASE_AX, 0xFFFFFFFF, 0xfc1c8)
            t.write32_mask(0x45D4 + CR_BASE_AX, 0xFFFFFFFF, 0xfdb053)
            t.write32_mask(0x45D8 + CR_BASE_AX, 0xFFFFFFFF, 0xf86f9a)
            t.write32_mask(0x45C0 + CR_BASE_AX, 0xFFFFFFFF, 0xfaef92)
            t.write32_mask(0x45C4 + CR_BASE_AX, 0xFFFFFFFF, 0xfe5fcc)
            t.write32_mask(0x45C8 + CR_BASE_AX, 0xFFFFFFFF, 0xffdff5)

    t.write32_mask(0x4738 + CR_BASE_AX, 1 << 17, 1 if is_2g else 0)           # R_PATH0_BAND_SEL_V1
    t.write32_mask(0x4AA4 + CR_BASE_AX, 1 << 17, 1 if is_2g else 0)           # R_PATH1_BAND_SEL_V1
    if is_2g:
        t.write32_clr(0x4970 + CR_BASE_AX, 1 << 1)                             # R_2P4G_BAND: B_2P4G_BAND_SEL = 0
    else:
        t.write32_set(0x4970 + CR_BASE_AX, 1 << 1)

    t.write32_mask(0x4E30 + CR_BASE_AX, 0x1FFF, freq)                         # R_FC0_V1
    sco = round((1 << 18) / freq)
    t.write32_mask(0x4974 + CR_BASE_AX, 0xC000007F, (bw << 30) | (sco & 0x7F))  # R_FC0_BW: BW + SCO
    t.write32_mask(0x4978 + CR_BASE_AX, 0x00000F00, (pri_ch & 0xF) << 8)       # R_CHBW_MOD: PRICH

    if bw == 1:                                                                # 40MHz 2XFFT & GI comb
        t.write32_mask(0x4E30 + CR_BASE_AX, 1 << 13, 1 << 13)
        t.write32_set(0x4424 + CR_BASE_AX, 1)
    else:
        t.write32_mask(0x4E30 + CR_BASE_AX, 1 << 13, 0)
        t.write32_clr(0x4424 + CR_BASE_AX, 1)

    # 6 GHz front-end control [SRC] rtw8852c.c:1928
    if is_6g:
        t.write32_set(0x40F8 + CR_BASE_AX, 1)                                  # R_MUIC: B_MUIC_EN
    else:
        t.write32_clr(0x40F8 + CR_BASE_AX, 1)

    t.write32_mask(0x0734 + CR_BASE_AX, 0xFF0000, ch)                         # R_MAC_PIN_SEL: B_CH_IDX_SEG0 = ch

    # ADC / WBADC 20M selection
    t.write32_mask(0xC0EC + CR_BASE_AX, 0x6000, 0)
    t.write32_mask(0xC0E4 + CR_BASE_AX, 0x30, 2)
    t.write32_mask(0xC1EC + CR_BASE_AX, 0x6000, 0)
    t.write32_mask(0xC1E4 + CR_BASE_AX, 0x30, 2)

    t.write32_mask(R_UPD_CLK_ADC + CR_BASE_AX, B_ENABLE_CCK, 1 if is_2g else 0)
    t.write32_mask(R_RXCCA_V1 + CR_BASE_AX, B_RXCCA_DIS_V1, 0 if is_2g else 1)
    t.write32_mask(R_PD_ARBITER_OFF + CR_BASE_AX, B_PD_ARBITER_OFF, 0 if is_2g else 1)
    # Secondary EDCCA per-20M bitmap for 20MHz [SRC] rtw8852c.c:1278-1285
    t.write32_mask(R_SNDCCA_A1 + CR_BASE_AX, B_SNDCCA_A1_EN, 0xFF)
    t.write32_mask(R_SNDCCA_A2 + CR_BASE_AX, B_SNDCCA_A2_VAL, 0x0)

    # Route BT/Wi-Fi antenna sharing for 2.4G
    ctrl_btg_bt_rx(t, is_2g)

    # BB reset async
    t.write32_mask(0x1200 + CR_BASE_AX, 0x70000000, 0x7)
    t.write32_mask(0x3200 + CR_BASE_AX, 0x70000000, 0x7)
    t.write32_set(0x0704 + CR_BASE_AX, 0x2)
    t.write32_clr(0x0704 + CR_BASE_AX, 0x2)
    t.write32_mask(0x1200 + CR_BASE_AX, 0x70000000, 0x0)
    t.write32_mask(0x3200 + CR_BASE_AX, 0x70000000, 0x0)
    t.write32_set(0x0704 + CR_BASE_AX, 0x2)

    # RF on Path A and Path B
    for path in (RF_PATH_A, RF_PATH_B):
        _ch_setting(t, path, ch, band, is_dav=True)
        _ch_setting(t, path, ch, band, is_dav=False)
        _bw_setting(t, path, bw=bw, is_dav=True, central_ch=ch, band=band)
        _bw_setting(t, path, bw=bw, is_dav=False, central_ch=ch, band=band)
        if path == RF_PATH_B:
            # Path B CHIP_CAV mirror sequence [SRC] rtw8852c_rfk.c:3888-3896
            write_rf(t, RF_PATH_B, RR_RSV1, RR_RSV1_RST, 0)
            tmp = read_rf(t, RF_PATH_A, RR_CFGCH, RFREG_MASK)
            write_rf(t, RF_PATH_B, RR_APK, RR_APK_MOD, 0x3)
            write_rf(t, RF_PATH_B, RR_CFGCH, RFREG_MASK, tmp)
            time.sleep(0.0001)
            write_rf(t, RF_PATH_B, RR_RSV1, RR_RSV1_RST, 1)
        _set_rxbb_bw(t, path, bw=bw)
    rf_enable_rx(t)

    # Enable RX path: ADC FIFO, packet detection, RX CCA
    bb_enable_rx(t, band)

    # Reset PMAC statistics and report counters
    pmac_stat_reset(t, is_2g)

    # Latch synthesizer to the active channel and bandwidth
    from . import rfk
    cfgch_bw = max(0, min(3 - bw, 3))
    chan_val = calc_cfgch_val(ch, band, cfgch_bw)
    rfk.lck(t, chan_val=chan_val)
    rfk.rx_dck(t)

    set_txpwr(t, band_is_2g=is_2g)

