"""RTL8852CU DLE/HFC and MAC trx setup.

The DLE (packet buffer) and HFC (flow control) blocks need their page pools and channel quotas
programmed before firmware download (the DLFW profile) and again when the MAC is brought up (the
SCC profile). dle_init()/hfc_init() take the profile; trx_init() then runs the AX DMAC/CMAC init
chain that the kernel's rtw89_mac_init() performs after firmware is running.

[SRC] mac.c:1194-1250 (hfc_init), 2050-2360 (dle_init), 2425-3080 (trx_init sub-inits),
rtw8852c.c:23-98 (hfc tables), 109-119 (SCC DLE rows), 3147-3162 (chip info).
"""
import time

from wifit3.errors import BringUpError

from .constants import (
    R_AX_DMAC_FUNC_EN, B_AX_MAC_FUNC_EN, B_AX_DMAC_FUNC_EN, B_AX_DLE_WDE_EN, B_AX_DLE_PLE_EN,
    R_AX_CMAC_FUNC_EN, R_AX_DMAC_CLK_EN, R_AX_DMAC_CLK_EN_WDE, B_AX_DLE_PLE_CLK_EN,
    R_AX_WDE_PKTBUF_CFG, B_AX_WDE_PAGE_SEL_MASK, B_AX_WDE_START_BOUND_MASK,
    B_AX_WDE_FREE_PAGE_NUM_MASK, S_AX_WDE_PAGE_SEL_64,
    R_AX_PLE_PKTBUF_CFG, B_AX_PLE_PAGE_SEL_MASK, B_AX_PLE_START_BOUND_MASK,
    B_AX_PLE_FREE_PAGE_NUM_MASK, S_AX_PLE_PAGE_SEL_128, DLE_BOUND_UNIT,
    R_AX_WDE_INI_STATUS, WDE_MGN_INI_RDY, R_AX_PLE_INI_STATUS, PLE_MGN_INI_RDY,
    R_AX_WDE_QTA0_CFG, R_AX_PLE_QTA0_CFG, B_AX_WDE_MIN_SIZE_MASK, B_AX_WDE_MAX_SIZE_MASK,
    B_AX_PLE_MIN_SIZE_MASK, B_AX_PLE_MAX_SIZE_MASK, DLE_WAIT_CNT,
    R_AX_HCI_FC_CTRL_V1, R_AX_CH_PAGE_CTRL_V1, B_AX_HCI_FC_EN, B_AX_HCI_FC_CH12_EN,
    B_AX_HCI_FC_MODE_MASK, B_AX_HCI_FC_WD_FULL_COND_MASK, B_AX_HCI_FC_WP_CH07_FULL_COND_MASK,
    B_AX_HCI_FC_WP_CH811_FULL_COND_MASK, B_AX_HCI_FC_CH12_FULL_COND_MASK,
    B_AX_PREC_PAGE_CH011_MASK, B_AX_PREC_PAGE_CH12_MASK,
    B_AX_PREC_PAGE_WP_CH07_MASK, B_AX_PREC_PAGE_WP_CH811_MASK,
    R_AX_ACH0_PAGE_CTRL_V1, R_AX_ACH0_PAGE_INFO_V1, R_AX_PUB_PAGE_CTRL1_V1,
    R_AX_PUB_PAGE_CTRL2_V1, R_AX_WP_PAGE_CTRL1_V1, R_AX_WP_PAGE_CTRL2_V1,
    R_AX_PUB_PAGE_INFO1_V1, R_AX_PUB_PAGE_INFO2_V1, R_AX_PUB_PAGE_INFO3_V1,
    R_AX_WP_PAGE_INFO1_V1, B_AX_MIN_PG_MASK, B_AX_MAX_PG_MASK, B_AX_GRP,
    B_AX_PUBPG_G0_MASK, B_AX_PUBPG_G1_MASK, B_AX_PUBPG_ALL_MASK, B_AX_WP_THRD_MASK,
    SCC_USB2_WDE_SIZE, SCC_USB2_PLE_SIZE, SCC_USB2_WDE_QT,
    SCC_USB2_PLE_MIN_QT, SCC_USB2_PLE_MAX_QT,
    SCC_USB3_WDE_SIZE, SCC_USB3_PLE_SIZE, SCC_USB3_WDE_QT,
    SCC_USB3_PLE_MIN_QT, SCC_USB3_PLE_MAX_QT,
    SCC_HFC_CH_CFG, SCC_HFC_PUB, SCC_HFC_PREC, HFC_MODE_STF, USB_SPEED_SUPER,
    DLFW_WDE_SIZE, DLFW_PLE_SIZE, DLFW_WDE_QT, DLFW_PLE_MIN_QT, DLFW_PLE_MAX_QT,
    # trx_init
    R_AX_SS_CTRL, B_AX_SS_EN, B_AX_SS_INIT_DONE_1, B_AX_SS_WARM_INIT_FLG,
    B_AX_SS_NONEMPTY_SS2FINFO_EN, TRXCFG_WAIT_CNT,
    R_AX_ACTION_FWD0, TRXCFG_MPDU_PROC_ACT_FRWD, R_AX_TF_FWD, TRXCFG_MPDU_PROC_TF_FRWD,
    R_AX_MPDU_PROC, B_AX_APPEND_FCS, B_AX_A_ICV_ERR, R_AX_CUT_AMSDU_CTRL,
    TRXCFG_MPDU_PROC_CUT_CTRL,
    R_AX_SEC_ENG_CTRL, B_AX_CLK_EN_CGCMP, B_AX_CLK_EN_WAPI, B_AX_CLK_EN_WEP_TKIP,
    B_AX_SEC_TX_ENC, B_AX_SEC_RX_DEC, B_AX_MC_DEC, B_AX_BC_DEC, B_AX_UC_MGNT_DEC,
    B_AX_TX_PARTIAL_MODE, R_AX_SEC_MPDU_PROC, B_AX_APPEND_ICV, B_AX_APPEND_MIC,
    R_AX_SEC_DEBUG1, B_AX_TX_TIMEOUT_SEL_MASK, AX_TX_TO_VAL,
    R_AX_ADDR_CAM_CTRL, B_AX_ADDR_CAM_RANGE_MASK, B_AX_ADDR_CAM_CLR, B_AX_ADDR_CAM_EN,
    R_AX_PREBKF_CFG_1, B_AX_SIFS_MACTXEN_T1_MASK, SIFS_MACTXEN_T1_V1,
    R_AX_CCA_CFG_0, B_AX_BTCCA_EN, R_AX_PREBKF_CFG_0, B_AX_PREBKF_TIME_MASK, SCH_PREBKF_24US,
    R_AX_MGNT_FLTR, R_AX_CTRL_FLTR, R_AX_DATA_FLTR, RX_FLTR_FRAME_TO_HOST,
    R_AX_RX_FLTR_OPT, R_AX_PLCP_HDR_FLTR, B_AX_CCK_CRC_CHK, B_AX_CCK_SIG_CHK,
    B_AX_LSIG_PARITY_CHK_EN, B_AX_SIGA_CRC_CHK, B_AX_VHT_SU_SIGB_CRC_CHK,
    B_AX_VHT_MU_SIGB_CRC_CHK, B_AX_HE_SIGB_CRC_CHK, DEFAULT_AX_RX_FLTR,
    R_AX_CCA_CONTROL, B_AX_TB_CHK_BASIC_NAV, B_AX_TB_CHK_BTCCA, B_AX_TB_CHK_EDCCA,
    B_AX_TB_CHK_CCA_P20, B_AX_SIFS_CHK_BTCCA, B_AX_SIFS_CHK_CCA_P20, B_AX_CTN_CHK_INTRA_NAV,
    B_AX_CTN_CHK_BASIC_NAV, B_AX_CTN_CHK_BTCCA, B_AX_CTN_CHK_EDCCA, B_AX_CTN_CHK_CCA_S80,
    B_AX_CTN_CHK_CCA_S40, B_AX_CTN_CHK_CCA_S20, B_AX_CTN_CHK_CCA_P20, B_AX_TB_CHK_TX_NAV,
    B_AX_TB_CHK_CCA_S80, B_AX_TB_CHK_CCA_S40, B_AX_TB_CHK_CCA_S20, B_AX_SIFS_CHK_CCA_S80,
    B_AX_SIFS_CHK_CCA_S40, B_AX_SIFS_CHK_CCA_S20, B_AX_CTN_CHK_TXNAV, B_AX_SIFS_CHK_EDCCA,
    B_AX_RSP_CHK_TXNAV, B_AX_RSP_CHK_INTRA_NAV, B_AX_RSP_CHK_BASIC_NAV,
    R_AX_TRXPTCL_RESP_0, B_AX_RSP_CHK_SEC_CCA_80, B_AX_RSP_CHK_SEC_CCA_40,
    B_AX_RSP_CHK_SEC_CCA_20, B_AX_RSP_CHK_BTCCA, B_AX_RSP_CHK_EDCCA, B_AX_RSP_CHK_CCA,
    R_AX_WMAC_NAV_CTL, B_AX_WMAC_PLCP_UP_NAV_EN, B_AX_WMAC_TF_UP_NAV_EN,
    B_AX_WMAC_NAV_UPPER_EN, B_AX_WMAC_NAV_UPPER_MASK, NAV_25MS,
    R_AX_RX_SR_CTRL, B_AX_SR_EN, R_AX_BSSID_SRC_CTRL, B_AX_PLCP_SRC_EN,
    R_AX_MAC_LOOPBACK, B_AX_MACLBK_EN, R_AX_TCR0, B_AX_TCR_UDF_THSD_MASK, TCR_UDF_THSD,
    R_AX_TXD_FIFO_CTRL, B_AX_TXDFIFO_HIGH_MCS_THRE_MASK, TXDFIFO_HIGH_MCS_THRE,
    B_AX_TXDFIFO_LOW_MCS_THRE_MASK, TXDFIFO_LOW_MCS_THRE,
    B_AX_WMAC_SPEC_SIFS_CCK_MASK, WMAC_SPEC_SIFS_CCK, B_AX_WMAC_SPEC_SIFS_OFDM_MASK,
    WMAC_SPEC_SIFS_OFDM_52C, R_AX_RXTRIG_TEST_USER_2, B_AX_RXTRIG_FCSCHK_EN,
    R_AX_TRXPTCL_RRSR_CTL_0, B_AX_WMAC_RESP_REF_RATE_SEL, R_AX_PTCL_RRSR1, B_AX_RSC_MASK,
    R_AX_RESPBA_CAM_CTRL, B_AX_BACAM_RST_MASK, S_AX_BACAM_RST_ALL, B_AX_SSN_SEL,
    R_AX_DLK_PROTECT_CTL, B_AX_RX_DLK_DATA_TIME_MASK, B_AX_RX_DLK_CCA_TIME_MASK,
    R_AX_RCR, B_AX_CH_EN_MASK, B_AX_RX_MPDU_MAX_LEN_MASK,
    R_AX_TX_SUB_CARRIER_VALUE, B_AX_TXSC_20M_MASK, B_AX_TXSC_40M_MASK, B_AX_TXSC_80M_MASK,
    R_AX_PTCL_COMMON_SETTING_0, B_AX_CMAC_TX_MODE_0, B_AX_CMAC_TX_MODE_1,
    B_AX_PTCL_TRIGGER_SS_EN_0, B_AX_PTCL_TRIGGER_SS_EN_1, B_AX_PTCL_TRIGGER_SS_EN_UL,
    R_AX_PTCLRPT_FULL_HDL, B_AX_SPE_RPT_PATH_MASK, FWD_TO_WLCPU,
    # IMR
    R_AX_WDRLS_ERR_IMR, B_AX_WDRLS_IMR_EN_CLR, B_AX_WDRLS_IMR_SET_V1,
    R_AX_SEC_ERROR_FLAG_IMR, B_AX_TX_HANG_IMR, B_AX_RX_HANG_IMR,
    R_AX_MPDU_TX_ERR_IMR, B_AX_TX_GET_ERRPKTID_INT_EN, B_AX_TX_NXT_ERRPKTID_INT_EN,
    B_AX_TX_MPDU_SIZE_ZERO_INT_EN, B_AX_TX_OFFSET_ERR_INT_EN, B_AX_TX_HDR3_SIZE_ERR_INT_EN,
    B_AX_TX_ETH_TYPE_ERR_EN, B_AX_TX_LLC_PRE_ERR_EN, B_AX_TX_NW_TYPE_ERR_EN,
    B_AX_TX_KSRCH_ERR_EN, B_AX_MPDU_TX_IMR_SET_V1,
    R_AX_MPDU_RX_ERR_IMR, B_AX_GETPKTID_ERR_INT_EN, B_AX_MHDRLEN_ERR_INT_EN, B_AX_RPT_ERR_INT_EN,
    B_AX_MPDU_RX_IMR_SET_V1, R_AX_STA_SCHEDULER_ERR_IMR, B_AX_SEARCH_HANG_TIMEOUT_INT_EN,
    B_AX_RPT_HANG_TIMEOUT_INT_EN, B_AX_PLE_B_PKTID_ERR_INT_EN, B_AX_STA_SCHEDULER_IMR_SET,
    R_AX_TXPKTCTL_B0_ERRFLAG_IMR, R_AX_TXPKTCTL_B1_ERRFLAG_IMR,
    B_AX_TXPKTCTL_IMR_B0_CLR_V1, B_AX_TXPKTCTL_IMR_B0_SET_V1,
    B_AX_TXPKTCTL_IMR_B1_CLR_V1, B_AX_TXPKTCTL_IMR_B1_SET_V1,
    R_AX_WDE_ERR_IMR, B_AX_WDE_IMR_CLR_V1, B_AX_WDE_IMR_SET_V1,
    R_AX_PLE_ERR_IMR, B_AX_PLE_IMR_CLR_V1, B_AX_PLE_IMR_SET_V1,
    R_AX_PKTIN_ERR_IMR, B_AX_PKTIN_GETPKTID_ERR_INT_EN,
    R_AX_HOST_DISPATCHER_ERR_IMR, B_AX_HOST_DISP_IMR_CLR_V1, B_AX_HOST_DISP_IMR_SET_V1,
    R_AX_CPU_DISPATCHER_ERR_IMR, B_AX_CPU_DISP_IMR_CLR_V1, B_AX_CPU_DISP_IMR_SET_V1,
    R_AX_OTHER_DISPATCHER_ERR_IMR, B_AX_OTHER_DISP_IMR_CLR_V1, B_AX_OTHER_DISP_IMR_SET_V1,
    R_AX_CPUIO_ERR_IMR, B_AX_CPUIO_IMR_SET,
    R_AX_BBRPT_COM_ERR_IMR, B_AX_BBRPT_COM_NULL_PLPKTID_ERR_INT_EN,
    R_AX_BBRPT_CHINFO_ERR_IMR, B_AX_BBRPT_CHINFO_IMR_CLR, R_AX_BBRPT_DFS_ERR_IMR, B_AX_BBRPT_DFS_TO_ERR_INT_EN,
    R_AX_LA_ERRFLAG, B_AX_LA_IMR_DATA_LOSS_ERR,
    R_AX_SCHEDULE_ERR_IMR, B_AX_SORT_NON_IDLE_ERR_INT_EN, B_AX_FSM_TIMEOUT_ERR_INT_EN,
    R_AX_PTCL_IMR0, B_AX_PTCL_IMR_CLR_V1, B_AX_PTCL_IMR_SET_V1,
    R_AX_RX_ERR_FLAG_IMR, B_AX_RX_ERR_IMR_CLR_V1, R_AX_TX_ERR_FLAG_IMR,
    B_AX_TX_ERR_IMR_CLR_V1, B_AX_TX_ERR_IMR_SET_V1,
    R_AX_PHYINFO_ERR_IMR_V1, B_AX_PHYINFO_IMR_CLR_V1, B_AX_PHYINFO_IMR_SET_V1,
    R_AX_RX_ERR_IMR, B_AX_RMAC_IMR_CLR_V1, B_AX_RMAC_IMR_SET_V1,
    R_AX_TRXPTCL_ERROR_INDICA_MASK, B_AX_TMAC_IMR_CLR_V1, B_AX_TMAC_IMR_SET_V1,
    B_AX_RX_ERR_IMR_SET_V1, B_AX_CPUIO_IMR_CLR, B_AX_BBRPT_CHINFO_IMR_SET_V1,
    R_AX_DMAC_ERR_IMR, R_AX_CMAC_ERR_IMR, DMAC_ERR_IMR_EN, CMAC0_ERR_IMR_EN,
    R_AX_WDRLS_CFG, B_AX_WDRLS_MODE_MASK, RPR_MODE_STF, R_AX_RLSRPT0_CFG0,
    B_AX_RLSRPT0_FLTR_MAP_MASK, R_AX_RLSRPT0_CFG1, B_AX_RLSRPT0_TO_MASK,
    B_AX_RLSRPT0_AGGNUM_MASK, R_AX_RSP_CHK_SIG, B_AX_RSP_STATIC_RTS_CHK_SERV_BW_EN,
)

PROFILE_DLFW = "dlfw"
PROFILE_SCC = "scc"


class _Profile:
    def __init__(self, wde_size, ple_size, wde_qt, ple_min, ple_max, hfc=None):
        self.wde_size = wde_size
        self.ple_size = ple_size
        self.wde_qt = wde_qt
        self.ple_min_qt = ple_min
        self.ple_max_qt = ple_max
        self.hfc = hfc


_DLFW_PROFILE = _Profile(DLFW_WDE_SIZE, DLFW_PLE_SIZE, DLFW_WDE_QT,
                         DLFW_PLE_MIN_QT, DLFW_PLE_MAX_QT)
# The kernel keeps one SCC quota mode and swaps the *row set* by HCI type (rtw89_hci_dle_type):
# the 8852C is the chip where USB 2.0 and USB 3.0 get different SCC DLE rows. DLFW is shared.
# [SRC] rtw8852c.c:109-132, 3173-3181; usb.c:1293-1296.
SCC_PROFILES = {
    False: _Profile(SCC_USB2_WDE_SIZE, SCC_USB2_PLE_SIZE, SCC_USB2_WDE_QT,
                    SCC_USB2_PLE_MIN_QT, SCC_USB2_PLE_MAX_QT,
                    (SCC_HFC_CH_CFG, SCC_HFC_PUB, SCC_HFC_PREC)),
    True: _Profile(SCC_USB3_WDE_SIZE, SCC_USB3_PLE_SIZE, SCC_USB3_WDE_QT,
                   SCC_USB3_PLE_MIN_QT, SCC_USB3_PLE_MAX_QT,
                   (SCC_HFC_CH_CFG, SCC_HFC_PUB, SCC_HFC_PREC)),
}


def is_usb3(t) -> bool:
    """Whether the transport runs on SuperSpeed (or above), which selects the USB3 DLE rows.
    [SRC] usb.c:1293-1296 rtw89_usb_dle_type."""
    return getattr(getattr(t, "dev", None), "speed", 0) >= USB_SPEED_SUPER


def profile_for(profile: str, usb3: bool = False) -> _Profile:
    if profile == PROFILE_DLFW:
        return _DLFW_PROFILE
    if profile == PROFILE_SCC:
        return SCC_PROFILES[bool(usb3)]
    raise KeyError(profile)


_PLE_KEYS = ("cma0_tx", "cma1_tx", "c2h", "h2c", "wcpu", "mpdu_proc",
             "cma0_dma", "cma1_dma", "bb_rpt", "wd_rel", "cpu_io", "tx_rpt", "h2d")


def _field(mask: int, val: int) -> int:
    return (val << ((mask & -mask).bit_length() - 1)) & mask


def _quota(min_val: int, max_val: int, min_mask: int, max_mask: int) -> int:
    return _field(min_mask, min_val) | _field(max_mask, max_val)


def _write_wde_quota(t, idx: int, min_val: int, max_val: int) -> None:
    t.write32(R_AX_WDE_QTA0_CFG + idx * 4,
              _quota(min_val, max_val, B_AX_WDE_MIN_SIZE_MASK, B_AX_WDE_MAX_SIZE_MASK))


def _write_ple_quota(t, idx: int, min_val: int, max_val: int) -> None:
    t.write32(R_AX_PLE_QTA0_CFG + idx * 4,
              _quota(min_val, max_val, B_AX_PLE_MIN_SIZE_MASK, B_AX_PLE_MAX_SIZE_MASK))


def _check_dmac(t) -> None:
    """rtw89_mac_check_mac_en(RTW89_MAC_0, RTW89_DMAC_SEL). [SRC] mac.c:62-84."""
    val = t.read32(R_AX_DMAC_FUNC_EN)
    if val in (0xFFFFFFFF, 0xDEADBEEF, 0x000000EA):
        raise BringUpError("dle", "DMAC is dead (EA/DEAD)")
    want = B_AX_MAC_FUNC_EN | B_AX_DMAC_FUNC_EN
    if (val & want) != want:
        raise BringUpError("dle", f"DMAC function block is not enabled (0x{val:08x})")


def _check_cmac(t) -> None:
    """rtw89_mac_check_mac_en(RTW89_MAC_0, RTW89_CMAC_SEL). [SRC] mac.c:62-84."""
    val = t.read32(R_AX_CMAC_FUNC_EN)
    if val in (0xFFFFFFFF, 0xDEADBEEF, 0x000000EA):
        raise BringUpError("trx", "CMAC is dead (EA/DEAD)")
    if not val & (1 << 30):
        raise BringUpError("trx", f"CMAC function block is not enabled (0x{val:08x})")


def _poll(addr: int, mask: int, t, what: str, budget_us: int = DLE_WAIT_CNT) -> None:
    deadline = time.monotonic() + budget_us / 1_000_000
    while True:
        val = t.read32(addr)
        if (val & mask) == mask:
            return
        if time.monotonic() >= deadline:
            raise BringUpError("dle", f"{what} not ready on 0x{addr:04x} (0x{val:08x})")


def _mix_cfg(t, prof: _Profile) -> None:
    """dle_mix_cfg_ax: page size + start bound + free page count for WDE and PLE.
    [SRC] mac.c:2093-2140."""
    wde_pge, wde_lnk, wde_unlnk = prof.wde_size
    ple_pge, ple_lnk, _ = prof.ple_size
    val = t.read32(R_AX_WDE_PKTBUF_CFG)
    val &= ~(B_AX_WDE_PAGE_SEL_MASK | B_AX_WDE_START_BOUND_MASK |
             B_AX_WDE_FREE_PAGE_NUM_MASK) & 0xFFFFFFFF
    val |= _field(B_AX_WDE_PAGE_SEL_MASK, S_AX_WDE_PAGE_SEL_64)
    val |= _field(B_AX_WDE_START_BOUND_MASK, 0)
    val |= _field(B_AX_WDE_FREE_PAGE_NUM_MASK, wde_lnk)
    t.write32(R_AX_WDE_PKTBUF_CFG, val)

    bound = (wde_lnk + wde_unlnk) * wde_pge // DLE_BOUND_UNIT
    val = t.read32(R_AX_PLE_PKTBUF_CFG)
    val &= ~(B_AX_PLE_PAGE_SEL_MASK | B_AX_PLE_START_BOUND_MASK |
             B_AX_PLE_FREE_PAGE_NUM_MASK) & 0xFFFFFFFF
    val |= _field(B_AX_PLE_PAGE_SEL_MASK, S_AX_PLE_PAGE_SEL_128)
    val |= _field(B_AX_PLE_START_BOUND_MASK, bound)
    val |= _field(B_AX_PLE_FREE_PAGE_NUM_MASK, ple_lnk)
    t.write32(R_AX_PLE_PKTBUF_CFG, val)


def _quota_cfg(t, prof: _Profile) -> None:
    """dle_quota_cfg -> wde_quota_cfg_ax + ple_quota_cfg_ax. [SRC] mac.c:2178-2205."""
    hif, wcpu, pkt_in, cpu_io = prof.wde_qt
    _write_wde_quota(t, 0, hif, hif)
    _write_wde_quota(t, 1, wcpu, wcpu)
    _write_wde_quota(t, 3, pkt_in, pkt_in)
    _write_wde_quota(t, 4, cpu_io, cpu_io)
    for idx, key in enumerate(_PLE_KEYS):
        _write_ple_quota(t, idx, prof.ple_min_qt[idx], prof.ple_max_qt[idx])


def dle_init(t, profile: str = PROFILE_DLFW, *, usb3: bool | None = None) -> None:
    """rtw89_mac_dle_init(mode): disable, clock on, size + quota config, enable, wait for the WDE
    and PLE managers to report ready. ``usb3`` picks the USB3 SCC row set; None reads it off the
    transport. [SRC] mac.c:2274-2345."""
    prof = profile_for(profile, is_usb3(t) if usb3 is None else usb3)
    _check_dmac(t)
    t.write32_clr(R_AX_DMAC_FUNC_EN, B_AX_DLE_WDE_EN | B_AX_DLE_PLE_EN)
    t.write32_set(R_AX_DMAC_CLK_EN, R_AX_DMAC_CLK_EN_WDE | B_AX_DLE_PLE_CLK_EN)
    _mix_cfg(t, prof)
    _quota_cfg(t, prof)
    t.write32_set(R_AX_DMAC_FUNC_EN, B_AX_DLE_WDE_EN | B_AX_DLE_PLE_EN)
    _poll(R_AX_WDE_INI_STATUS, WDE_MGN_INI_RDY, t, "WDE init")
    _poll(R_AX_PLE_INI_STATUS, PLE_MGN_INI_RDY, t, "PLE init")


def _hfc_h2c_cfg(t, prec) -> None:
    t.write32_mask(R_AX_CH_PAGE_CTRL_V1, B_AX_PREC_PAGE_CH12_MASK, prec[1])
    t.write32_mask(R_AX_HCI_FC_CTRL_V1, B_AX_HCI_FC_CH12_FULL_COND_MASK, prec[5])


def _hfc_func_en(t, en: bool, h2c_en: bool) -> None:
    val = t.read32(R_AX_HCI_FC_CTRL_V1)
    if en:
        val |= B_AX_HCI_FC_EN
    else:
        val &= ~B_AX_HCI_FC_EN & 0xFFFFFFFF
    if h2c_en:
        val |= B_AX_HCI_FC_CH12_EN
    else:
        val &= ~B_AX_HCI_FC_CH12_EN & 0xFFFFFFFF
    t.write32(R_AX_HCI_FC_CTRL_V1, val)


def _hfc_ch_ctrl(t, ch: int, cfg) -> None:
    mn, mx, grp = cfg[ch]
    val = _field(B_AX_MIN_PG_MASK, mn) | _field(B_AX_MAX_PG_MASK, mx)
    if grp:
        val |= B_AX_GRP
    t.write32(R_AX_ACH0_PAGE_CTRL_V1 + ch * 4, val)


def _hfc_pub_ctrl(t, pub) -> None:
    grp0, grp1, _pub_max, wp_thrd = pub
    t.write32(R_AX_PUB_PAGE_CTRL1_V1,
              _field(B_AX_PUBPG_G0_MASK, grp0) | _field(B_AX_PUBPG_G1_MASK, grp1))
    t.write32(R_AX_WP_PAGE_CTRL2_V1, _field(B_AX_WP_THRD_MASK, wp_thrd))


def _hfc_mix_cfg(t, pub, prec) -> None:
    """hfc_mix_cfg_ax. [SRC] mac.c:1140-1175."""
    val = (_field(B_AX_PREC_PAGE_CH011_MASK, prec[0]) |
           _field(B_AX_PREC_PAGE_CH12_MASK, prec[1]))
    t.write32(R_AX_CH_PAGE_CTRL_V1, val)
    t.write32(R_AX_PUB_PAGE_CTRL2_V1, _field(B_AX_PUBPG_ALL_MASK, pub[2]))
    val = (_field(B_AX_PREC_PAGE_WP_CH07_MASK, prec[2]) |
           _field(B_AX_PREC_PAGE_WP_CH811_MASK, prec[3]))
    t.write32(R_AX_WP_PAGE_CTRL1_V1, val)
    val = t.read32(R_AX_HCI_FC_CTRL_V1)
    val = (val & ~B_AX_HCI_FC_MODE_MASK & 0xFFFFFFFF) | _field(B_AX_HCI_FC_MODE_MASK, HFC_MODE_STF)
    val = (val & ~B_AX_HCI_FC_WD_FULL_COND_MASK & 0xFFFFFFFF) | \
        _field(B_AX_HCI_FC_WD_FULL_COND_MASK, prec[4])
    val = (val & ~B_AX_HCI_FC_CH12_FULL_COND_MASK & 0xFFFFFFFF) | \
        _field(B_AX_HCI_FC_CH12_FULL_COND_MASK, prec[5])
    val = (val & ~B_AX_HCI_FC_WP_CH07_FULL_COND_MASK & 0xFFFFFFFF) | \
        _field(B_AX_HCI_FC_WP_CH07_FULL_COND_MASK, prec[6])
    val = (val & ~B_AX_HCI_FC_WP_CH811_FULL_COND_MASK & 0xFFFFFFFF) | \
        _field(B_AX_HCI_FC_WP_CH811_FULL_COND_MASK, prec[7])
    t.write32(R_AX_HCI_FC_CTRL_V1, val)


def hfc_init(t, profile: str = PROFILE_DLFW, *, usb3: bool | None = None) -> None:
    """rtw89_mac_hfc_init(reset=true, en, h2c_en).

    DLFW: the download path only flow-controls H2C; the profile's ch_cfg is NULL and the kernel's
    (en=false, h2c_en=true) early return programs just H2C.
    SCC: full channel/public config with both engines enabled. The USB2 and USB3 entries of
    qta_def.hfc_param_ini point at the same table, so ``usb3`` changes nothing today.
    [SRC] mac.c:1194-1250, rtw8852c.c:53-99."""
    prof = profile_for(profile, is_usb3(t) if usb3 is None else usb3)
    _check_dmac(t)
    _hfc_func_en(t, False, False)

    if prof.hfc is None:
        prec = (None, 32, None, None, None, 1, None, None)
        _hfc_h2c_cfg(t, prec)
        _hfc_func_en(t, False, True)
        return

    ch_cfg, pub, prec = prof.hfc
    for ch in range(12):                      # RTW89_DMA_ACH0 .. B1HI (excludes H2C)
        _hfc_ch_ctrl(t, ch, ch_cfg)
    _hfc_pub_ctrl(t, pub)
    _hfc_mix_cfg(t, pub, prec)
    _hfc_func_en(t, True, True)
    time.sleep(0.00001)                       # udelay(10)
    for ch in range(12):
        _ = t.read32(R_AX_ACH0_PAGE_INFO_V1 + ch * 4)   # hfc_upd_ch_info
    # hfc_get_mix_info_ax: refreshes the cached public-page counters after init.
    t.read32(R_AX_PUB_PAGE_INFO1_V1)
    t.read32(R_AX_PUB_PAGE_INFO3_V1)
    t.read32(R_AX_PUB_PAGE_INFO2_V1)
    t.read32(R_AX_WP_PAGE_INFO1_V1)


# ---------------------------------------------------------------------------------------------
# trx_init: rtw89_mac_init's DMAC + CMAC chain after firmware download.
# ---------------------------------------------------------------------------------------------

def _imr_enable(t) -> None:
    """enable_imr_ax(DMAC_SEL) + enable_imr_ax(CMAC_SEL) + err_imr_ctrl_ax(true).
    [SRC] mac.c:3744-3975."""
    t.write32_clr(R_AX_WDRLS_ERR_IMR, B_AX_WDRLS_IMR_EN_CLR)
    t.write32_set(R_AX_WDRLS_ERR_IMR, B_AX_WDRLS_IMR_SET_V1)

    t.write32_set(R_AX_SEC_ERROR_FLAG_IMR, B_AX_TX_HANG_IMR | B_AX_RX_HANG_IMR)

    t.write32_clr(R_AX_MPDU_TX_ERR_IMR,
                  B_AX_TX_GET_ERRPKTID_INT_EN | B_AX_TX_NXT_ERRPKTID_INT_EN |
                  B_AX_TX_MPDU_SIZE_ZERO_INT_EN | B_AX_TX_OFFSET_ERR_INT_EN |
                  B_AX_TX_HDR3_SIZE_ERR_INT_EN)
    t.write32_clr(R_AX_MPDU_TX_ERR_IMR,
                  B_AX_TX_ETH_TYPE_ERR_EN | B_AX_TX_LLC_PRE_ERR_EN |
                  B_AX_TX_NW_TYPE_ERR_EN | B_AX_TX_KSRCH_ERR_EN)
    t.write32_set(R_AX_MPDU_TX_ERR_IMR, B_AX_MPDU_TX_IMR_SET_V1)
    t.write32_clr(R_AX_MPDU_RX_ERR_IMR,
                  B_AX_GETPKTID_ERR_INT_EN | B_AX_MHDRLEN_ERR_INT_EN | B_AX_RPT_ERR_INT_EN)
    t.write32_set(R_AX_MPDU_RX_ERR_IMR, B_AX_MPDU_RX_IMR_SET_V1)

    t.write32_clr(R_AX_STA_SCHEDULER_ERR_IMR,
                  B_AX_SEARCH_HANG_TIMEOUT_INT_EN | B_AX_RPT_HANG_TIMEOUT_INT_EN |
                  B_AX_PLE_B_PKTID_ERR_INT_EN)
    t.write32_set(R_AX_STA_SCHEDULER_ERR_IMR, B_AX_STA_SCHEDULER_IMR_SET)

    t.write32_clr(R_AX_TXPKTCTL_B0_ERRFLAG_IMR, B_AX_TXPKTCTL_IMR_B0_CLR_V1)
    t.write32_set(R_AX_TXPKTCTL_B0_ERRFLAG_IMR, B_AX_TXPKTCTL_IMR_B0_SET_V1)
    t.write32_clr(R_AX_TXPKTCTL_B1_ERRFLAG_IMR, B_AX_TXPKTCTL_IMR_B1_CLR_V1)
    t.write32_set(R_AX_TXPKTCTL_B1_ERRFLAG_IMR, B_AX_TXPKTCTL_IMR_B1_SET_V1)

    t.write32_clr(R_AX_WDE_ERR_IMR, B_AX_WDE_IMR_CLR_V1)
    t.write32_set(R_AX_WDE_ERR_IMR, B_AX_WDE_IMR_SET_V1)
    t.write32_clr(R_AX_PLE_ERR_IMR, B_AX_PLE_IMR_CLR_V1)
    t.write32_set(R_AX_PLE_ERR_IMR, B_AX_PLE_IMR_SET_V1)
    t.write32_set(R_AX_PKTIN_ERR_IMR, B_AX_PKTIN_GETPKTID_ERR_INT_EN)

    t.write32_clr(R_AX_HOST_DISPATCHER_ERR_IMR, B_AX_HOST_DISP_IMR_CLR_V1)
    t.write32_set(R_AX_HOST_DISPATCHER_ERR_IMR, B_AX_HOST_DISP_IMR_SET_V1)
    t.write32_clr(R_AX_CPU_DISPATCHER_ERR_IMR, B_AX_CPU_DISP_IMR_CLR_V1)
    t.write32_set(R_AX_CPU_DISPATCHER_ERR_IMR, B_AX_CPU_DISP_IMR_SET_V1)
    t.write32_clr(R_AX_OTHER_DISPATCHER_ERR_IMR, B_AX_OTHER_DISP_IMR_CLR_V1)
    t.write32_set(R_AX_OTHER_DISPATCHER_ERR_IMR, B_AX_OTHER_DISP_IMR_SET_V1)

    t.write32_clr(R_AX_CPUIO_ERR_IMR, B_AX_CPUIO_IMR_CLR)
    t.write32_set(R_AX_CPUIO_ERR_IMR, B_AX_CPUIO_IMR_SET)

    t.write32_set(R_AX_BBRPT_COM_ERR_IMR, B_AX_BBRPT_COM_NULL_PLPKTID_ERR_INT_EN)
    t.write32_clr(R_AX_BBRPT_CHINFO_ERR_IMR, B_AX_BBRPT_CHINFO_IMR_CLR)
    t.write32_set(R_AX_BBRPT_CHINFO_ERR_IMR, B_AX_BBRPT_CHINFO_IMR_SET_V1)
    t.write32_set(R_AX_BBRPT_DFS_ERR_IMR, B_AX_BBRPT_DFS_TO_ERR_INT_EN)
    t.write32_set(R_AX_LA_ERRFLAG, B_AX_LA_IMR_DATA_LOSS_ERR)

    # CMAC
    t.write32_clr(R_AX_SCHEDULE_ERR_IMR,
                  B_AX_SORT_NON_IDLE_ERR_INT_EN | B_AX_FSM_TIMEOUT_ERR_INT_EN)
    t.write32_set(R_AX_SCHEDULE_ERR_IMR, B_AX_FSM_TIMEOUT_ERR_INT_EN)
    t.write32_clr(R_AX_PTCL_IMR0, B_AX_PTCL_IMR_CLR_V1)
    t.write32_set(R_AX_PTCL_IMR0, B_AX_PTCL_IMR_SET_V1)
    t.write32_clr(R_AX_RX_ERR_FLAG_IMR, B_AX_RX_ERR_IMR_CLR_V1)
    t.write32_set(R_AX_RX_ERR_FLAG_IMR, B_AX_RX_ERR_IMR_SET_V1)
    t.write32_clr(R_AX_TX_ERR_FLAG_IMR, B_AX_TX_ERR_IMR_CLR_V1)
    t.write32_set(R_AX_TX_ERR_FLAG_IMR, B_AX_TX_ERR_IMR_SET_V1)
    t.write32_clr(R_AX_PHYINFO_ERR_IMR_V1, B_AX_PHYINFO_IMR_CLR_V1)
    t.write32_set(R_AX_PHYINFO_ERR_IMR_V1, B_AX_PHYINFO_IMR_SET_V1)
    t.write32_clr(R_AX_RX_ERR_IMR, B_AX_RMAC_IMR_CLR_V1)
    t.write32_set(R_AX_RX_ERR_IMR, B_AX_RMAC_IMR_SET_V1)
    t.write32_clr(R_AX_TRXPTCL_ERROR_INDICA_MASK, B_AX_TMAC_IMR_CLR_V1)
    t.write32_set(R_AX_TRXPTCL_ERROR_INDICA_MASK, B_AX_TMAC_IMR_SET_V1)

    t.write32(R_AX_DMAC_ERR_IMR, DMAC_ERR_IMR_EN)
    t.write32(R_AX_CMAC_ERR_IMR, CMAC0_ERR_IMR_EN)


def _sta_sch_init(t) -> None:
    val = t.read8(R_AX_SS_CTRL) | B_AX_SS_EN
    t.write8(R_AX_SS_CTRL, val)
    deadline = time.monotonic() + TRXCFG_WAIT_CNT / 1_000_000
    while not t.read32(R_AX_SS_CTRL) & B_AX_SS_INIT_DONE_1:
        if time.monotonic() >= deadline:
            raise BringUpError("trx", "STA scheduler init timed out")
    t.write32_set(R_AX_SS_CTRL, B_AX_SS_WARM_INIT_FLG)
    t.write32_clr(R_AX_SS_CTRL, B_AX_SS_NONEMPTY_SS2FINFO_EN)


def _mpdu_proc_init(t) -> None:
    t.write32(R_AX_ACTION_FWD0, TRXCFG_MPDU_PROC_ACT_FRWD)
    t.write32(R_AX_TF_FWD, TRXCFG_MPDU_PROC_TF_FRWD)
    t.write32_set(R_AX_MPDU_PROC, B_AX_APPEND_FCS | B_AX_A_ICV_ERR)
    t.write32(R_AX_CUT_AMSDU_CTRL, TRXCFG_MPDU_PROC_CUT_CTRL)


def _sec_eng_init(t) -> None:
    val = t.read32(R_AX_SEC_ENG_CTRL)
    val |= B_AX_CLK_EN_CGCMP | B_AX_CLK_EN_WAPI | B_AX_CLK_EN_WEP_TKIP
    val |= B_AX_SEC_TX_ENC | B_AX_SEC_RX_DEC | B_AX_MC_DEC | B_AX_BC_DEC | B_AX_UC_MGNT_DEC
    val &= ~B_AX_TX_PARTIAL_MODE & 0xFFFFFFFF
    t.write32(R_AX_SEC_ENG_CTRL, val)
    t.write32(R_AX_SEC_MPDU_PROC, t.read32(R_AX_SEC_MPDU_PROC) | B_AX_APPEND_ICV | B_AX_APPEND_MIC)
    t.write32_mask(R_AX_SEC_DEBUG1, B_AX_TX_TIMEOUT_SEL_MASK, AX_TX_TO_VAL)


def _addr_cam_init(t) -> None:
    val = t.read32(R_AX_ADDR_CAM_CTRL)
    val |= _field(B_AX_ADDR_CAM_RANGE_MASK, 0x7F) | B_AX_ADDR_CAM_CLR | B_AX_ADDR_CAM_EN
    t.write32(R_AX_ADDR_CAM_CTRL, val)
    deadline = time.monotonic() + TRXCFG_WAIT_CNT / 1_000_000
    while t.read16(R_AX_ADDR_CAM_CTRL) & B_AX_ADDR_CAM_CLR:
        if time.monotonic() >= deadline:
            raise BringUpError("trx", "ADDR CAM reset timed out")


def _scheduler_init(t) -> None:
    t.write32_mask(R_AX_PREBKF_CFG_1, B_AX_SIFS_MACTXEN_T1_MASK, SIFS_MACTXEN_T1_V1)
    t.write32_clr(R_AX_CCA_CFG_0, B_AX_BTCCA_EN)
    if not (t.read32(R_AX_SEC_ENG_CTRL) & B_AX_TX_PARTIAL_MODE):
        t.write32_mask(R_AX_PREBKF_CFG_0, B_AX_PREBKF_TIME_MASK, SCH_PREBKF_24US)


def _rx_fltr_init(t) -> None:
    for reg in (R_AX_MGNT_FLTR, R_AX_CTRL_FLTR, R_AX_DATA_FLTR):
        t.write32(reg, RX_FLTR_FRAME_TO_HOST)
    t.write32(R_AX_RX_FLTR_OPT, DEFAULT_AX_RX_FLTR)
    t.write16(R_AX_PLCP_HDR_FLTR,
              B_AX_CCK_CRC_CHK | B_AX_CCK_SIG_CHK | B_AX_LSIG_PARITY_CHK_EN |
              B_AX_SIGA_CRC_CHK | B_AX_VHT_SU_SIGB_CRC_CHK | B_AX_VHT_MU_SIGB_CRC_CHK |
              B_AX_HE_SIGB_CRC_CHK)


def _patch_dis_resp_chk(t) -> None:
    nav = B_AX_RSP_CHK_TXNAV | B_AX_RSP_CHK_INTRA_NAV | B_AX_RSP_CHK_BASIC_NAV
    cca = (B_AX_RSP_CHK_SEC_CCA_80 | B_AX_RSP_CHK_SEC_CCA_40 | B_AX_RSP_CHK_SEC_CCA_20 |
           B_AX_RSP_CHK_BTCCA | B_AX_RSP_CHK_EDCCA | B_AX_RSP_CHK_CCA)
    t.write32(R_AX_RSP_CHK_SIG, t.read32(R_AX_RSP_CHK_SIG) | nav)
    t.write32(R_AX_TRXPTCL_RESP_0, t.read32(R_AX_TRXPTCL_RESP_0) | cca)


def _cca_ctrl_init(t) -> None:
    val = t.read32(R_AX_CCA_CONTROL)
    val |= (B_AX_TB_CHK_BASIC_NAV | B_AX_TB_CHK_BTCCA | B_AX_TB_CHK_EDCCA |
            B_AX_TB_CHK_CCA_P20 | B_AX_SIFS_CHK_BTCCA | B_AX_SIFS_CHK_CCA_P20 |
            B_AX_CTN_CHK_INTRA_NAV | B_AX_CTN_CHK_BASIC_NAV | B_AX_CTN_CHK_BTCCA |
            B_AX_CTN_CHK_EDCCA | B_AX_CTN_CHK_CCA_S80 | B_AX_CTN_CHK_CCA_S40 |
            B_AX_CTN_CHK_CCA_S20 | B_AX_CTN_CHK_CCA_P20)
    val &= ~(B_AX_TB_CHK_TX_NAV | B_AX_TB_CHK_CCA_S80 | B_AX_TB_CHK_CCA_S40 |
             B_AX_TB_CHK_CCA_S20 | B_AX_SIFS_CHK_CCA_S80 | B_AX_SIFS_CHK_CCA_S40 |
             B_AX_SIFS_CHK_CCA_S20 | B_AX_CTN_CHK_TXNAV | B_AX_SIFS_CHK_EDCCA) & 0xFFFFFFFF
    t.write32(R_AX_CCA_CONTROL, val)
    _patch_dis_resp_chk(t)


def _nav_ctrl_init(t) -> None:
    t.write32_set(R_AX_WMAC_NAV_CTL,
                  B_AX_WMAC_PLCP_UP_NAV_EN | B_AX_WMAC_TF_UP_NAV_EN | B_AX_WMAC_NAV_UPPER_EN)
    t.write32_mask(R_AX_WMAC_NAV_CTL, B_AX_WMAC_NAV_UPPER_MASK, NAV_25MS)


def _spatial_reuse_init(t) -> None:
    t.write8_clr(R_AX_RX_SR_CTRL, B_AX_SR_EN)
    t.write8_set(R_AX_BSSID_SRC_CTRL, B_AX_PLCP_SRC_EN)


def _tmac_init(t) -> None:
    t.write32_clr(R_AX_MAC_LOOPBACK, B_AX_MACLBK_EN)
    t.write32_mask(R_AX_TCR0, B_AX_TCR_UDF_THSD_MASK, TCR_UDF_THSD)
    t.write32_mask(R_AX_TXD_FIFO_CTRL,
                   B_AX_TXDFIFO_HIGH_MCS_THRE_MASK, TXDFIFO_HIGH_MCS_THRE)
    t.write32_mask(R_AX_TXD_FIFO_CTRL,
                   B_AX_TXDFIFO_LOW_MCS_THRE_MASK, TXDFIFO_LOW_MCS_THRE)


def _trxptcl_init(t) -> None:
    val = t.read32(R_AX_TRXPTCL_RESP_0)
    val &= ~B_AX_WMAC_SPEC_SIFS_CCK_MASK & 0xFFFFFFFF
    val |= _field(B_AX_WMAC_SPEC_SIFS_CCK_MASK, WMAC_SPEC_SIFS_CCK)
    val &= ~B_AX_WMAC_SPEC_SIFS_OFDM_MASK & 0xFFFFFFFF
    val |= _field(B_AX_WMAC_SPEC_SIFS_OFDM_MASK, WMAC_SPEC_SIFS_OFDM_52C)
    t.write32(R_AX_TRXPTCL_RESP_0, val)
    t.write32_set(R_AX_RXTRIG_TEST_USER_2, B_AX_RXTRIG_FCSCHK_EN)
    t.write32_mask(R_AX_TRXPTCL_RRSR_CTL_0, B_AX_WMAC_RESP_REF_RATE_SEL, 0)
    t.write32_mask(R_AX_PTCL_RRSR1, B_AX_RSC_MASK, 2)


def _rmac_init(t, rx_qta: int, ple_pg_size: int) -> None:
    t.write32_mask(R_AX_RESPBA_CAM_CTRL, B_AX_BACAM_RST_MASK, S_AX_BACAM_RST_ALL)
    deadline = time.monotonic() + 0.001
    while t.read32_mask(R_AX_RESPBA_CAM_CTRL, B_AX_BACAM_RST_MASK):
        if time.monotonic() >= deadline:
            break        # kernel only warns; a stuck BA CAM must not abort bring-up
    t.write8_set(R_AX_RESPBA_CAM_CTRL, B_AX_SSN_SEL)

    val = t.read16(R_AX_DLK_PROTECT_CTL)
    val &= ~(B_AX_RX_DLK_DATA_TIME_MASK | B_AX_RX_DLK_CCA_TIME_MASK) & 0xFFFF
    val |= _field(B_AX_RX_DLK_DATA_TIME_MASK, 15) | _field(B_AX_RX_DLK_CCA_TIME_MASK, 32)
    t.write16(R_AX_DLK_PROTECT_CTL, val)

    t.write8_mask(R_AX_RCR, B_AX_CH_EN_MASK, 0x1)

    rx_max_len = min(rx_qta, 127) * ple_pg_size
    rx_max_len = min(rx_max_len, 11454 + 512) // 512
    t.write32_mask(R_AX_RX_FLTR_OPT, B_AX_RX_MPDU_MAX_LEN_MASK, rx_max_len)
    t.write8_clr(R_AX_PLCP_HDR_FLTR, B_AX_VHT_SU_SIGB_CRC_CHK)


def _cmac_com_init(t) -> None:
    val = t.read32(R_AX_TX_SUB_CARRIER_VALUE)
    val &= ~(B_AX_TXSC_20M_MASK | B_AX_TXSC_40M_MASK | B_AX_TXSC_80M_MASK) & 0xFFFFFFFF
    t.write32(R_AX_TX_SUB_CARRIER_VALUE, val)


def _ptcl_init(t) -> None:
    t.write8_set(R_AX_PTCL_COMMON_SETTING_0, B_AX_CMAC_TX_MODE_0 | B_AX_CMAC_TX_MODE_1)
    t.write8_clr(R_AX_PTCL_COMMON_SETTING_0,
                 B_AX_PTCL_TRIGGER_SS_EN_0 | B_AX_PTCL_TRIGGER_SS_EN_1 |
                 B_AX_PTCL_TRIGGER_SS_EN_UL)
    t.write8_mask(R_AX_PTCLRPT_FULL_HDL, B_AX_SPE_RPT_PATH_MASK, FWD_TO_WLCPU)


def _set_host_rpr(t) -> None:
    """set_host_rpr_ax for a USB (STF) host. [SRC] mac.c:4010-4032."""
    t.write32_mask(R_AX_WDRLS_CFG, B_AX_WDRLS_MODE_MASK, RPR_MODE_STF)
    t.write32_clr(R_AX_RLSRPT0_CFG0, B_AX_RLSRPT0_FLTR_MAP_MASK)
    t.write32_mask(R_AX_RLSRPT0_CFG1, B_AX_RLSRPT0_AGGNUM_MASK, 30)
    t.write32_mask(R_AX_RLSRPT0_CFG1, B_AX_RLSRPT0_TO_MASK, 255)


def trx_init(t, *, usb3: bool | None = None) -> None:
    """rtw89_mac_trx_init on AX: DMAC then CMAC init chain. The SCC DLE rows (and therefore the
    RX quota the max MPDU length derives from) depend on the bus speed, so a SuperSpeed link runs
    the USB3 tables. [SRC] mac.c:4019-4090, 2591-3090; usb.c:1293-1296."""
    usb3 = is_usb3(t) if usb3 is None else usb3
    prof = profile_for(PROFILE_SCC, usb3)
    # DMAC
    dle_init(t, PROFILE_SCC, usb3=usb3)
    hfc_init(t, PROFILE_SCC, usb3=usb3)
    _sta_sch_init(t)
    _mpdu_proc_init(t)
    _sec_eng_init(t)
    # CMAC: every kernel sub-init re-checks the CMAC block first; one check covers the chain.
    _check_cmac(t)
    _scheduler_init(t)
    _addr_cam_init(t)
    _rx_fltr_init(t)
    _cca_ctrl_init(t)
    _nav_ctrl_init(t)
    _spatial_reuse_init(t)
    _tmac_init(t)
    _trxptcl_init(t)
    _rmac_init(t, prof.ple_min_qt[6], prof.ple_size[0])
    _cmac_com_init(t)
    _ptcl_init(t)
    # enable_imr_ax(DMAC) + enable_imr_ax(CMAC) + err_imr_ctrl_ax(true)
    _imr_enable(t)
    _set_host_rpr(t)
    # this chip is a single-MAC (STF) USB device; kernel clears the static-RTS check here.
    t.write32_clr(R_AX_RSP_CHK_SIG, B_AX_RSP_STATIC_RTS_CHK_SERV_BW_EN)
