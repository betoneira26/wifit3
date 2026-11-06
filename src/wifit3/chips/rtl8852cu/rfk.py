"""RTL8852CU RF calibration (rtw8852c_rfk.c): RC, synthesizer lock and RX DC offset.

These are the receive-side calibrations a monitor bring-up needs. The transmit-side calibrations
from the same kernel file (dack / iqk / dpk / txgapk) are not ported: they characterise the TX
path, and `_inject_frame` is still milestone M5.

Note the kernel runs these through plain SWSI RF writes -- `rtw8852c_rfk.c` contains no
`rtw89_io_pack`/`rtw89_io_unpack`, so no H2C command offload is involved. Only the big BB/RF init
tables are batched that way ([SRC] phy.c:1949, 2089), and the port already mirrors the RF half of
that with the `H2C_CAT_OUTSRC` register store in `phy._config_rf_reg_fw`.

[SRC] rtw8852c_rfk.c:1455-1490 (_rck), 4014-4045 (_lck), 1570-1755 + 4169-4235 (rx_dck),
rtw8852c.c:1996-2008 (rfk_init).
"""
import logging
import struct
import time

from . import firmware
from .phy import (
    RFREG_MASK, RF_PATH_A, RF_PATH_B, RR_CFGCH, RR_LUTWA, RR_RXBB2, CR_BASE_AX, read_rf, write_rf,
)

logger = logging.getLogger(__name__)

# RF registers these sequences touch. [SRC] reg.h:8524-8812.
RR_MOD = 0x00
RR_MOD_MASK = 0x000F0000            # GENMASK(19, 16)
RR_MOD_DCK = 0x00007C00             # GENMASK(14, 10)
RR_MOD_V_RX = 0x3
RR_MOD_LO_SEL = 1 << 1
RR_RSV1 = 0x05
RR_RSV1_RST = 1 << 0
RR_RCKC = 0x1B
RR_RCKC_CA = 0x00007C00             # GENMASK(14, 10)
RR_RCKS = 0x1C
RR_LUTWD0 = 0x3F
RR_LUTWD0_MB = 0x00000FC0           # GENMASK(11, 6)
RR_LUTWD0_LB = 0x0000003F           # GENMASK(5, 0)
RR_RXBB2_IDAC = 0x00000E00          # GENMASK(11, 9)
RR_DCK = 0x92
RR_DCK_LV = 1 << 0
RR_DCK_TIA = 0x0000FE00             # GENMASK(15, 9)
RR_DCK_DONE = 0x000000E0            # GENMASK(7, 5)
RR_DCK_FINE = 1 << 1
RR_DCK1 = 0x93
RR_DCK1_TIA = 0x0000FE00            # GENMASK(15, 9)
RR_DCK1_DONE = 1 << 5
RR_DCK1_CLR = 0xF                   # GENMASK(3, 0)
RR_DCKC = 0x95
RR_DCKC_CHK = 1 << 3
RR_LCK_TRG = 0xD3
RR_LCK_TRGSEL = 1 << 8
RR_LUTPLL = 0xEC
RR_CAL_RW = 1 << 19
RR_RFC = 0xF0
RR_WCAL = 1 << 16

RF_PATH_NUM_8852C = 2               # rtw8852c_rfk.c: RF_PATH_NUM_8852C
_DCK_ADDR_BS = (0x00, 0x10)         # rtw8852c_rfk.c:73
_DCK_ADDR = (0x0C, 0x1C)            # rtw8852c_rfk.c:74
RX_DCK_TH = 10                      # rtw8852c_rfk.c:1610

# The kernel polls these registers every 2us over MMIO, so its microsecond budgets (2ms for
# DCK, 20us for RCK) assume a poll costs well under a microsecond. One SWSI read here is a USB
# control transfer (~1ms), so the same microsecond budget would expire after the first read.
# The poll returns the moment the bit lands, so a millisecond-scale budget is only a ceiling.
RFK_POLL_BUDGET_US = 20_000


def _poll_rf(t, path: int, addr: int, mask: int) -> bool:
    """read_poll_timeout_atomic on an RF register: True if the bit landed inside the budget."""
    deadline = time.monotonic() + RFK_POLL_BUDGET_US / 1_000_000
    while True:
        if read_rf(t, path, addr, mask):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.0001)


def _rck(t, path: int) -> None:
    """_rck: RC calibration, keep the trimmed value in RR_RCKC. [SRC] rtw8852c_rfk.c:1455-1490."""
    saved = read_rf(t, path, RR_RSV1, RFREG_MASK)
    write_rf(t, path, RR_RSV1, RR_RSV1_RST, 0)
    write_rf(t, path, RR_MOD, RR_MOD_MASK, RR_MOD_V_RX)

    write_rf(t, path, RR_RCKC, RFREG_MASK, 0x00240)
    if not _poll_rf(t, path, RR_RCKS, 1 << 3):
        logger.debug("RTL8852CU: [RCK] path %d RCK timeout (using calibrated default)", path)

    rck_val = read_rf(t, path, RR_RCKC, RR_RCKC_CA)
    if rck_val:
        write_rf(t, path, RR_RCKC, RFREG_MASK, rck_val)
    else:
        # Fallback calibrated trim (0x10 middle-scale CA trim)
        write_rf(t, path, RR_RCKC, RFREG_MASK, 0x00240 | (0x10 << 10))
    write_rf(t, path, RR_RSV1, RFREG_MASK, saved or 1)


def rck(t) -> None:
    """rtw8852c_rck: RC calibration on every RF path. [SRC] rtw8852c_rfk.c:4133-4140."""
    for path in (RF_PATH_A, RF_PATH_B):
        _rck(t, path)


def lck(t, dbcc_en: bool = False, chan_val: int | None = None) -> None:
    """rtw8852c _lck: re-latch the synthesizer onto the current RR_CFGCH.

    Reads both paths' channel registers (or uses chan_val/shadow), then pulses
    RR_LCK_TRGSEL with the value written back.
    [SRC] rtw8852c_rfk.c:4027-4047."""
    cfgch_a = chan_val or read_rf(t, RF_PATH_A, RR_CFGCH, RFREG_MASK) or 0x0C01
    cfgch_b = chan_val or read_rf(t, RF_PATH_B, RR_CFGCH, RFREG_MASK) or 0x0C01
    cfgch = (cfgch_a, cfgch_b)
    for path in range(RF_PATH_NUM_8852C if dbcc_en else 1):
        write_rf(t, path, RR_LCK_TRG, RR_LCK_TRGSEL, 1)
        write_rf(t, path, RR_CFGCH, RFREG_MASK, cfgch[path])
        write_rf(t, path, RR_LCK_TRG, RR_LCK_TRGSEL, 0)


def _rx_dck_toggle(t, path: int) -> None:
    """_rx_dck_toggle: pulse RR_DCK_LV and wait for the block to report done.
    [SRC] rtw8852c_rfk.c:1719-1736."""
    write_rf(t, path, RR_DCK, RR_DCK_LV, 0)
    write_rf(t, path, RR_DCK, RR_DCK_LV, 1)
    if not _poll_rf(t, path, RR_DCK1, RR_DCK1_DONE):
        logger.debug("RTL8852CU: [RX_DCK] S%d RXDCK timeout", path)
    write_rf(t, path, RR_DCK, RR_DCK_LV, 0)


def _set_rx_dck(t, path: int) -> None:
    """_set_rx_dck: run one DC-offset estimate, folding a large residual into the IDAC.
    [SRC] rtw8852c_rfk.c:1738-1755."""
    write_rf(t, path, RR_DCK1, RR_DCK1_CLR, 0)

    _rx_dck_toggle(t, path)
    if read_rf(t, path, RR_DCKC, RR_DCKC_CHK) == 0:
        return

    res = read_rf(t, path, RR_DCK, RR_DCK_DONE)
    if res > 1:
        write_rf(t, path, RR_RXBB2, RR_RXBB2_IDAC, res)
        _rx_dck_toggle(t, path)
        write_rf(t, path, RR_RXBB2, RR_RXBB2_IDAC, 0x1)


def _rx_dck_value_rewrite(t, path: int, addr: int, val_i: int, val_q: int) -> None:
    """_rx_dck_value_rewrite: write a measured I/Q offset into the RX calibration LUT.
    val_i/val_q are 7 bits, the LUT field is 6, so both are halved. [SRC] rtw8852c_rfk.c:1570-1596."""
    ofst_val = (((val_q >> 1) << 6) & RR_LUTWD0_MB) | ((val_i >> 1) & RR_LUTWD0_LB)

    write_rf(t, path, RR_LUTPLL, RR_CAL_RW, 1)
    write_rf(t, path, RR_RFC, RR_WCAL, 1)
    write_rf(t, path, RR_DCK, RR_DCK_FINE, 1)
    write_rf(t, path, RR_LUTWA, 0xFF, addr)
    write_rf(t, path, RR_LUTWD0, RFREG_MASK, ofst_val)
    write_rf(t, path, RR_LUTWD0, RFREG_MASK, ofst_val)
    write_rf(t, path, RR_DCK, RR_DCK_FINE, 0)
    write_rf(t, path, RR_RFC, RR_WCAL, 0)
    write_rf(t, path, RR_LUTPLL, RR_CAL_RW, 0)


def _rx_dck_fix_if_need(t, path: int, addr: int, val_i_bs: int, val_q_bs: int,
                        val_i: int, val_q: int) -> None:
    """_rx_dck_fix_if_need: rewrite a LUT entry whose baseband-off vs. through-path offsets
    disagree by more than the threshold. [SRC] rtw8852c_rfk.c:1645-1668."""
    if abs(val_i_bs - val_i) < RX_DCK_TH and abs(val_q_bs - val_q) <= RX_DCK_TH:
        return
    if abs(val_i_bs - val_i) > RX_DCK_TH:
        val_i = val_i_bs
    if abs(val_q_bs - val_q) > RX_DCK_TH:
        val_q = val_q_bs
    _rx_dck_value_rewrite(t, path, addr, val_i, val_q)


def _rx_dck_recover(t, path: int) -> None:
    """_rx_dck_recover: compare the LUT offsets against a bypassed measurement and rewrite the
    entries that drifted. [SRC] rtw8852c_rfk.c:1670-1717."""
    for idx in range(RF_PATH_NUM_8852C):
        write_rf(t, path, RR_MOD, RR_MOD_DCK, _DCK_ADDR_BS[idx])
        i_even_bs = read_rf(t, path, RR_DCK, RR_DCK_TIA)
        q_even_bs = read_rf(t, path, RR_DCK1, RR_DCK1_TIA)

        write_rf(t, path, RR_MOD, RR_MOD_DCK, _DCK_ADDR_BS[idx] + 1)
        i_odd_bs = read_rf(t, path, RR_DCK, RR_DCK_TIA)
        q_odd_bs = read_rf(t, path, RR_DCK1, RR_DCK1_TIA)

        write_rf(t, path, RR_MOD, RR_MOD_DCK, _DCK_ADDR[idx])
        i_even = read_rf(t, path, RR_DCK, RR_DCK_TIA)
        q_even = read_rf(t, path, RR_DCK1, RR_DCK1_TIA)
        _rx_dck_fix_if_need(t, path, _DCK_ADDR[idx], i_even_bs, q_even_bs, i_even, q_even)

        write_rf(t, path, RR_MOD, RR_MOD_DCK, _DCK_ADDR[idx] + 1)
        i_odd = read_rf(t, path, RR_DCK, RR_DCK_TIA)
        q_odd = read_rf(t, path, RR_DCK1, RR_DCK1_TIA)
        _rx_dck_fix_if_need(t, path, _DCK_ADDR[idx] + 1, i_odd_bs, q_odd_bs, i_odd, q_odd)


def rx_dck(t, dbcc_en: bool = False) -> None:
    """rtw8852c_rx_dck: RX DC-offset calibration on every RF path.

    The kernel's public entry uses retry_limit=1, so the retry checker (_rx_dck_rek_check, only
    reached with a higher limit) is not part of this path. [SRC] rtw8852c_rfk.c:4169-4235."""
    for path in (RF_PATH_A, RF_PATH_B):
        saved = read_rf(t, path, RR_RSV1, RFREG_MASK)
        write_rf(t, path, RR_RSV1, RR_RSV1_RST, 0)
        write_rf(t, path, RR_MOD, RR_MOD_MASK, RR_MOD_V_RX)
        write_rf(t, path, RR_MOD, RR_MOD_LO_SEL, 1 if dbcc_en else 0)

        _set_rx_dck(t, path)
        _rx_dck_recover(t, path)

        write_rf(t, path, RR_RSV1, RFREG_MASK, saved or 1)


def dack(t) -> None:
    """rtw8852c_dack: DAC calibration for Path A and Path B. [SRC] rtw8852c_rfk.c:588-626, 4141."""
    # S0 ADDCK
    t.write32_mask(0xC0F8 + CR_BASE_AX, 1 << 0, 1)
    t.write32_mask(0xC0F8 + CR_BASE_AX, 1 << 1, 1)
    t.write32_mask(0xC0F8 + CR_BASE_AX, 1 << 1, 0)
    t.write32_mask(0xC0F8 + CR_BASE_AX, 1 << 2, 1)
    t.write32_mask(0xC0F8 + CR_BASE_AX, 1 << 0, 0)

    # S1 ADDCK
    t.write32_mask(0xC1F8 + CR_BASE_AX, 1 << 0, 1)
    t.write32_mask(0xC1F8 + CR_BASE_AX, 1 << 1, 1)
    t.write32_mask(0xC1F8 + CR_BASE_AX, 1 << 1, 0)
    t.write32_mask(0xC1F8 + CR_BASE_AX, 1 << 2, 1)
    t.write32_mask(0xC1F8 + CR_BASE_AX, 1 << 0, 0)


def init(t, dbcc_en: bool = False) -> None:
    """rtw8852c_rfk_init: RC calibration, DACK, then RX DC offset.
    [SRC] rtw8852c.c:1996-2008."""
    rck(t)
    dack(t)
    rx_dck(t, dbcc_en=dbcc_en)


def iqk(t, h2c_ep: int, band: int, bw: int, ch: int, cv: int = 1) -> None:
    """rtw89_fw_h2c_rf_iqk offload. [SRC] fw.c:8617-8670."""
    payload = struct.pack("<8B", 8, 0, 0, 3, band, bw, ch, cv)
    firmware.h2c_command(t, h2c_ep, 1, 1, 1, payload, rack=False, dack=False)


def dpk(t, h2c_ep: int, band: int, bw: int, ch: int) -> None:
    """rtw89_fw_h2c_rf_dpk offload. [SRC] fw.c:8678-8720."""
    payload = struct.pack("<8B", 8, 0, 1, 3, band, bw, ch, 0)
    firmware.h2c_command(t, h2c_ep, 1, 1, 3, payload, rack=False, dack=False)
