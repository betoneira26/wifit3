"""RTL8852CU chip power, ported from rtw8852c.c (pwr_on_func / pwr_off_func) and mac.c
(power_switch). The cold-boot order is the kernel's, verbatim; don't reorder.
"""
import time

from wifit3.errors import BringUpError

from . import firmware, trx
from .constants import (
    R_AX_SYS_STATUS1, B_AX_PAD_HCI_SEL_V2_MASK, MAC_AX_HCI_SEL_PCIE_USB,
    R_AX_LDO_AON_CTRL0, B_AX_PD_REGU_L, R_AX_SYS_PW_CTRL, B_AX_AFSM_WLSUS_EN,
    B_AX_AFSM_PCIE_SUS_EN, B_AX_DIS_WLBT_PDNSUSEN_SOPC, B_AX_APDM_HPDN,
    B_AX_APFM_SWLPS, R_AX_WLLPS_CTRL, B_AX_DIS_WLBT_LPSEN_LOPC,
    R_AX_SPS_DIG_ON_CTRL0, B_AX_OCP_L1_MASK, B_AX_RDY_SYSPWR, B_AX_EN_WLON,
    B_AX_APFN_ONMAC, R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN, R_AX_SYS_SDIO_CTRL,
    B_AX_PCIE_CALIB_EN_V1, R_AX_SYS_ISO_CTRL_EXTEND, B_AX_CMAC1_FEN,
    B_AX_R_SYM_ISO_CMAC12PP, R_AX_AFE_CTRL1, B_AX_R_SYM_WLCMAC1_P4_PC_EN,
    B_AX_R_SYM_WLCMAC1_P3_PC_EN, B_AX_R_SYM_WLCMAC1_P2_PC_EN,
    B_AX_R_SYM_WLCMAC1_P1_PC_EN, B_AX_R_SYM_WLCMAC1_PC_EN,
    R_AX_SYS_ADIE_PAD_PWR_CTRL, B_AX_SYM_PADPDN_WL_PTA_1P3,
    B_AX_SYM_PADPDN_WL_RFC_1P3, R_AX_PMC_DBG_CTRL2, B_AX_SYSON_DIS_PMCR_AX_WRMSK,
    R_AX_SYS_ISO_CTRL, B_AX_ISO_EB2CORE, B_AX_PWC_EV2EF_B15, B_AX_PWC_EV2EF_B14,
    R_AX_GPIO0_15_EECS_EESK_LED1_PULL_LOW_EN, B_AX_LED1_PULL_LOW_EN,
    B_AX_EESK_PULL_LOW_EN, B_AX_EECS_PULL_LOW_EN, R_AX_DMAC_FUNC_EN,
    B_AX_MAC_FUNC_EN, B_AX_DMAC_FUNC_EN, B_AX_MPDU_PROC_EN, B_AX_WD_RLS_EN,
    B_AX_DLE_WDE_EN, B_AX_TXPKT_CTRL_EN, B_AX_STA_SCH_EN, B_AX_DLE_PLE_EN,
    B_AX_PKT_BUF_EN, B_AX_DMAC_TBL_EN, B_AX_PKT_IN_EN, B_AX_DLE_CPUIO_EN,
    B_AX_DISPATCHER_EN, B_AX_BBRPT_EN, B_AX_MAC_SEC_EN, B_AX_MAC_UN_EN,
    R_AX_CMAC_FUNC_EN, B_AX_CMAC_EN, B_AX_CMAC_TXEN,
    B_AX_CMAC_RXEN, B_AX_FORCE_CMACREG_GCKEN, B_AX_PHYINTF_EN, B_AX_CMAC_DMA_EN,
    B_AX_PTCLTOP_EN, B_AX_SCHEDULER_EN, B_AX_TMAC_EN, B_AX_RMAC_EN,
    R_AX_LED1_FUNC_SEL, B_AX_PINMUX_EESK_FUNC_SEL_V1_MASK,
    PINMUX_EESK_FUNC_SEL_BT_LOG, B_AX_APFM_OFFMAC, SW_LPS_OPTION,
    B_AX_XTAL_OFF_A_DIE, R_AX_WLRF_CTRL, B_AX_AFC_AFEDIG, R_AX_SYS_FUNC_EN,
    B_AX_FEN_BB_GLB_RSTN, B_AX_FEN_BBRSTB, B_AX_R_SYM_FEN_WLBBGLB_1,
    B_AX_R_SYM_FEN_WLBBFUN_1, B_AX_REG_ZCDC_H_MASK, R_AX_SYS_SWR_CTRL1,
    B_AX_SYM_CTRL_SPS_PWMFREQ, R_AX_GPIO_MUXCFG, B_AX_BOOT_MODE, B_AX_AUTO_WLPON,
    R_AX_RSV_CTRL, B_AX_R_DIS_PRST, R_AX_SCOREBOARD, MAC_AX_NOTIFY_TP_MAJOR, MAC_AX_NOTIFY_PWR_MAJOR,
    R_AX_WCPU_FW_CTRL, B_AX_WCPU_FWDL_EN, B_AX_H2C_PATH_RDY, B_AX_FWDL_PATH_RDY,
    B_AX_WCPU_FWDL_STS_MASK, B_AX_WCPU_EN, R_AX_SYS_CLK_CTRL, B_AX_CPU_CLK_EN,
    R_AX_UDM1, R_AX_UDM2, R_AX_HALT_H2C_CTRL, R_AX_HALT_C2H_CTRL, R_AX_HALT_H2C,
    R_AX_HALT_C2H, R_AX_H2CREG_CTRL_V1, R_AX_C2HREG_CTRL_V1,
    R_AX_BOOT_REASON, B_AX_BOOT_REASON_MASK, RTW89_FWDL_INITIAL_STATE,
    R_AX_HCI_FUNC_EN_V1, B_AX_HCI_RXDMA_EN, B_AX_HCI_TXDMA_EN, R_AX_DMAC_CLK_EN,
    B_AX_DISPATCHER_CLK_EN, R_AX_HAXI_INIT_CFG1, B_AX_DMA_MODE_MASK, B_AX_STOP_AXI_MST,
    B_AX_RXHCI_EN_V1, B_AX_TXHCI_EN_V1, DMA_MOD_USB, B_AX_AXIDMA_EN,
    R_AX_HAXI_DMA_STOP1, B_AX_STOP_WPDMA, B_AX_STOP_CH12, B_AX_STOP_CH9, B_AX_STOP_CH8,
    B_AX_STOP_ACH0, B_AX_STOP_ACH1, B_AX_STOP_ACH2,
    B_AX_STOP_ACH3, B_AX_STOP_ACH4, B_AX_STOP_ACH5, B_AX_STOP_ACH6, B_AX_STOP_ACH7,
    R_AX_HAXI_DMA_STOP2, B_AX_STOP_CH10, B_AX_STOP_CH11, B_AX_H_AXIDMA_EN,
    R_AX_USB_HOST_REQUEST_2_V1, B_AX_R_USBIO_MODE_V1, R_AX_USB_WLAN0_1_V1,
    B_AX_USBRX_RST_V1, B_AX_USBTX_RST_V1,
    XTAL_SI_ANAPAR_WL, XTAL_SI_GND_SHDN_WL, XTAL_SI_SHDN_WL, XTAL_SI_RFC2RF,
    XTAL_SI_OFF_EI, XTAL_SI_OFF_WEI, XTAL_SI_PON_EI, XTAL_SI_PON_WEI,
    XTAL_SI_SRAM2RFC, XTAL_SI_WL_RFC_S0, XTAL_SI_RF00, XTAL_SI_WL_RFC_S1,
    XTAL_SI_RF10, XTAL_SI_XTAL_XMD_2, XTAL_SI_XTAL_XMD_4, XTAL_SI_LDO_LPS,
    XTAL_SI_LPS_CAP,
    RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE, RTW89_FWCMD_C2HREG_FUNC_PHY_CAP,
    RTW89_C2HREG_PHYCAP_W0_RX_NSS, RTW89_C2HREG_PHYCAP_W1_TX_NSS,
    RTW89_C2HREG_PHYCAP_W1_PROT, RTW89_C2HREG_PHYCAP_W1_PROT_11BE,
    RTW89_C2HREG_PHYCAP_W3_ANT_TX_NUM, RTW89_C2HREG_PHYCAP_W3_ANT_RX_NUM,
    RTW89_8852C_TX_NSS, RTW89_8852C_RX_NSS, RF_B,
    R_AX_CK_EN, B_AX_DMAC_CRPRT, B_AX_MAC_SEC_CLK_EN, B_AX_DLE_CPUIO_CLK_EN,
    B_AX_PKT_IN_CLK_EN, B_AX_STA_SCH_CLK_EN, B_AX_TXPKT_CTRL_CLK_EN,
    B_AX_WD_RLS_CLK_EN, B_AX_BBRPT_CLK_EN, B_AX_CMAC_CKEN, B_AX_PHYINTF_CKEN,
    B_AX_CMAC_DMA_CKEN, B_AX_PTCLTOP_CKEN, B_AX_SCHEDULER_CKEN, B_AX_TMAC_CKEN,
    B_AX_RMAC_CKEN, B_AX_CMAC_CRPRT,
    R_AX_AFE_OFF_CTRL1, B_AX_S0_LDO_VSEL_F_MASK, B_AX_S1_LDO_VSEL_F_MASK,
    XTAL0, XTAL3, FULL_BIT_MASK,
    R_AX_USB3_MAC_NPI_CONFIG_INTF_0_V1, B_AX_SSPHY_LFPS_FILTER_V1,
    R_AX_USB_ENDPOINT_0_V1, R_AX_USB_ENDPOINT_2_NUMP_V1, B_AX_EP_IDX_V1,
    R_AX_RXDMA_SETTING, USB2_BULKSIZE, USB3_BULKSIZE, NUMP, R_AX_RXAGG_0_V1, R_AX_RXAGG_1_V1,
    B_AX_RXAGG_0_EN,
    R_AX_CTRL_FLTR, R_AX_MGNT_FLTR, R_AX_DATA_FLTR, RX_FLTR_FRAME_TO_HOST,
    R_AX_RX_FLTR_OPT, B_AX_RX_FLTR_CFG_MASK, SNIFFER_AX_RX_FLTR,
    R_AX_RCR, B_AX_STOP_RX_IN, B_AX_CH_EN_MASK,
    R_AX_PPDU_STAT, R_AX_HW_RPT_FWD,
    R_AX_P0MB_HGQ_WINDOW_CFG_0, R_AX_MD_TSFT_STMP_CTL, R_AX_MBSSID_CTRL,
    R_AX_MBSSID_DROP_0, R_AX_PTCL_BSS_COLOR_0, B_AX_BCN_DROP_ALLOW,
    R_AX_FILTER_MODEL_ADDR, R_AX_INDIR_ACCESS_ENTRY,
    DMAC_TBL_BASE_ADDR, CMAC_TBL_BASE_ADDR, CCTL_INFO_SIZE,
)


class RTL8852CUMac:
    """Chip power switching for the rtw89 8852C."""

    def __init__(self, transport):
        self.t = transport

    def _poll(self, addr: int, ready, attempts: int = 20) -> bool:
        """read_poll_timeout(read32, cond, 1ms interval, 20ms timeout). mac.c passim."""
        for _ in range(attempts):
            if ready(self.t.read32(addr)):
                return True
            time.sleep(0.001)
        return ready(self.t.read32(addr))

    def power_switch_boot_mode(self) -> None:
        """rtw89_mac_power_switch_boot_mode: USB only. [SRC] mac.c:1444-1456."""
        if not self.t.read32_mask(R_AX_GPIO_MUXCFG, B_AX_BOOT_MODE):
            return
        self.t.write32_clr(R_AX_SYS_PW_CTRL, B_AX_APFN_ONMAC)
        self.t.write32_clr(R_AX_SYS_STATUS1, B_AX_AUTO_WLPON)
        self.t.write32_clr(R_AX_GPIO_MUXCFG, B_AX_BOOT_MODE)
        self.t.write32_clr(R_AX_RSV_CTRL, B_AX_R_DIS_PRST)

    def pwr_on_func(self) -> bool:
        """rtw8852c_pwr_on_func. [SRC] rtw8852c.c:211-331."""
        t = self.t
        if t.read32_mask(R_AX_SYS_STATUS1, B_AX_PAD_HCI_SEL_V2_MASK) == MAC_AX_HCI_SEL_PCIE_USB:
            t.write32_set(R_AX_LDO_AON_CTRL0, B_AX_PD_REGU_L)

        t.write32_clr(R_AX_SYS_PW_CTRL, B_AX_AFSM_WLSUS_EN | B_AX_AFSM_PCIE_SUS_EN)
        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_DIS_WLBT_PDNSUSEN_SOPC)
        t.write32_set(R_AX_WLLPS_CTRL, B_AX_DIS_WLBT_LPSEN_LOPC)
        t.write32_clr(R_AX_SYS_PW_CTRL, B_AX_APDM_HPDN)
        t.write32_clr(R_AX_SYS_PW_CTRL, B_AX_APFM_SWLPS)

        t.write32_mask(R_AX_SPS_DIG_ON_CTRL0, B_AX_OCP_L1_MASK, 0x7)

        if not self._poll(R_AX_SYS_PW_CTRL, lambda v: v & B_AX_RDY_SYSPWR):
            return False

        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_EN_WLON)
        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_APFN_ONMAC)

        if not self._poll(R_AX_SYS_PW_CTRL, lambda v: not v & B_AX_APFN_ONMAC):
            return False

        t.write8_set(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)
        t.write8_clr(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)
        t.write8_set(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)
        t.write8_clr(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)

        t.write8_set(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)
        t.write32_clr(R_AX_SYS_SDIO_CTRL, B_AX_PCIE_CALIB_EN_V1)

        t.write32_clr(R_AX_SYS_ISO_CTRL_EXTEND, B_AX_CMAC1_FEN)
        t.write32_set(R_AX_SYS_ISO_CTRL_EXTEND, B_AX_R_SYM_ISO_CMAC12PP)
        t.write32_clr(R_AX_AFE_CTRL1, B_AX_R_SYM_WLCMAC1_P4_PC_EN |
                      B_AX_R_SYM_WLCMAC1_P3_PC_EN | B_AX_R_SYM_WLCMAC1_P2_PC_EN |
                      B_AX_R_SYM_WLCMAC1_P1_PC_EN | B_AX_R_SYM_WLCMAC1_PC_EN)
        t.write32_set(R_AX_SYS_ADIE_PAD_PWR_CTRL, B_AX_SYM_PADPDN_WL_PTA_1P3)

        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_GND_SHDN_WL, XTAL_SI_GND_SHDN_WL)
        t.write32_set(R_AX_SYS_ADIE_PAD_PWR_CTRL, B_AX_SYM_PADPDN_WL_RFC_1P3)

        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_SHDN_WL, XTAL_SI_SHDN_WL)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_OFF_WEI, XTAL_SI_OFF_WEI)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_OFF_EI, XTAL_SI_OFF_EI)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_RFC2RF)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_PON_WEI, XTAL_SI_PON_WEI)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_PON_EI, XTAL_SI_PON_EI)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_SRAM2RFC)
        t.write_xtal_si(XTAL_SI_XTAL_XMD_2, 0x10, XTAL_SI_LDO_LPS)
        t.write_xtal_si(XTAL_SI_XTAL_XMD_4, 0, XTAL_SI_LPS_CAP)

        t.write32_set(R_AX_PMC_DBG_CTRL2, B_AX_SYSON_DIS_PMCR_AX_WRMSK)
        t.write32_set(R_AX_SYS_ISO_CTRL, B_AX_ISO_EB2CORE)
        t.write32_clr(R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B15)

        time.sleep(0.001)  # fsleep(1000)

        t.write32_clr(R_AX_SYS_ISO_CTRL, B_AX_PWC_EV2EF_B14)
        t.write32_clr(R_AX_PMC_DBG_CTRL2, B_AX_SYSON_DIS_PMCR_AX_WRMSK)
        t.write32_set(R_AX_GPIO0_15_EECS_EESK_LED1_PULL_LOW_EN,
                      B_AX_EECS_PULL_LOW_EN | B_AX_EESK_PULL_LOW_EN | B_AX_LED1_PULL_LOW_EN)

        t.write32_set(R_AX_DMAC_FUNC_EN,
                      B_AX_MAC_FUNC_EN | B_AX_DMAC_FUNC_EN | B_AX_MPDU_PROC_EN |
                      B_AX_WD_RLS_EN | B_AX_DLE_WDE_EN | B_AX_TXPKT_CTRL_EN |
                      B_AX_STA_SCH_EN | B_AX_DLE_PLE_EN | B_AX_PKT_BUF_EN |
                      B_AX_DMAC_TBL_EN | B_AX_PKT_IN_EN | B_AX_DLE_CPUIO_EN |
                      B_AX_DISPATCHER_EN | B_AX_BBRPT_EN | B_AX_MAC_SEC_EN |
                      B_AX_MAC_UN_EN | B_AX_H_AXIDMA_EN)

        t.write32_set(R_AX_CMAC_FUNC_EN,
                      B_AX_CMAC_EN | B_AX_CMAC_TXEN | B_AX_CMAC_RXEN |
                      B_AX_FORCE_CMACREG_GCKEN | B_AX_PHYINTF_EN |
                      B_AX_CMAC_DMA_EN | B_AX_PTCLTOP_EN | B_AX_SCHEDULER_EN |
                      B_AX_TMAC_EN | B_AX_RMAC_EN)

        t.write32_mask(R_AX_LED1_FUNC_SEL, B_AX_PINMUX_EESK_FUNC_SEL_V1_MASK,
                       PINMUX_EESK_FUNC_SEL_BT_LOG)
        return True

    def pwr_off_func(self) -> bool:
        """rtw8852c_pwr_off_func. [SRC] rtw8852c.c:332-397."""
        t = self.t
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_RFC2RF, XTAL_SI_RFC2RF)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_OFF_EI)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_OFF_WEI)
        t.write_xtal_si(XTAL_SI_WL_RFC_S0, 0, XTAL_SI_RF00)
        t.write_xtal_si(XTAL_SI_WL_RFC_S1, 0, XTAL_SI_RF10)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, XTAL_SI_SRAM2RFC, XTAL_SI_SRAM2RFC)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_PON_EI)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_PON_WEI)

        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_EN_WLON)
        t.write32_clr(R_AX_WLRF_CTRL, B_AX_AFC_AFEDIG)
        t.write8_clr(R_AX_SYS_FUNC_EN, B_AX_FEN_BB_GLB_RSTN | B_AX_FEN_BBRSTB)
        t.write32_clr(R_AX_SYS_ISO_CTRL_EXTEND, B_AX_R_SYM_FEN_WLBBGLB_1 | B_AX_R_SYM_FEN_WLBBFUN_1)
        t.write32_clr(R_AX_SYS_ADIE_PAD_PWR_CTRL, B_AX_SYM_PADPDN_WL_RFC_1P3)

        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_SHDN_WL)
        t.write32_clr(R_AX_SYS_ADIE_PAD_PWR_CTRL, B_AX_SYM_PADPDN_WL_PTA_1P3)
        t.write_xtal_si(XTAL_SI_ANAPAR_WL, 0, XTAL_SI_GND_SHDN_WL)

        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_APFM_OFFMAC)
        if not self._poll(R_AX_SYS_PW_CTRL, lambda v: not v & B_AX_APFM_OFFMAC):
            return False

        t.write32(R_AX_WLLPS_CTRL, SW_LPS_OPTION)
        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_XTAL_OFF_A_DIE)
        t.write32_set(R_AX_SYS_SWR_CTRL1, B_AX_SYM_CTRL_SPS_PWMFREQ)
        t.write32_mask(R_AX_SPS_DIG_ON_CTRL0, B_AX_REG_ZCDC_H_MASK, 0x3)
        t.write32_set(R_AX_SYS_PW_CTRL, B_AX_APFM_SWLPS)
        return True

    def power_switch(self, on: bool) -> bool:
        """rtw89_mac_power_switch. [SRC] mac.c:1521-1588. The 8852C uses rtw89_mac_gen_ax, whose
        reset_pwr_state is only a *check* (mac.c:4109): MAC_ON on USB replies -EAGAIN so the
        caller power-cycles, which exists for the ZeroCD mass-storage handover. The blacklist
        keeps any driver from touching this card, so there is no prior owner to reset away, and
        pwr_on_func runs cleanly over the chip's default MAC_ON state (verified on the card:
        returns True, CV reads 0x1). A power-cycle is avoided on purpose: powering this built-in
        card down detaches it from USB until the machine loses power."""
        self.power_switch_boot_mode()
        ok = self.pwr_on_func() if on else self.pwr_off_func()
        if not ok:
            return False
        if on:
            self.t.write8(R_AX_SCOREBOARD + 3, MAC_AX_NOTIFY_TP_MAJOR)
        else:
            self.t.write8(R_AX_SCOREBOARD + 3, MAC_AX_NOTIFY_PWR_MAJOR)
        return True

    def pwr_on(self) -> bool:
        """rtw89_mac_pwr_on: one attempt, no retry. [SRC] mac.c:1517-1528."""
        return self.power_switch(True)

    def pwr_off(self) -> None:
        """rtw89_mac_pwr_off. [SRC] mac.c:1532-1534."""
        self.power_switch(False)

    def disable_cpu(self) -> None:
        """rtw89_mac_disable_cpu_ax. Disables CPU, FWDL paths, CPU clock, WDT, and toggles PLATFORM_EN.
        [SRC] mac.c:4151-4163."""
        t = self.t
        t.write32_clr(R_AX_PLATFORM_ENABLE, B_AX_WCPU_EN)
        t.write32_clr(R_AX_WCPU_FW_CTRL,
                      B_AX_WCPU_FWDL_EN | B_AX_H2C_PATH_RDY | B_AX_FWDL_PATH_RDY)
        t.write32_clr(R_AX_SYS_CLK_CTRL, B_AX_CPU_CLK_EN)

        # rtw89_disable_fw_watchdog [SRC] mac.c:4140-4150
        try:
            t.write32(0x0C04, 0x18003000 + 0x0040)
            t.write32(0x40000, 0)
            t.write32(0x0C04, 0x18003000 + 0x0044)
            val = t.read32(0x40000)
            val = (val | (1 << 8)) & ~(1 << 0)
            t.write32(0x0C04, 0x18003000 + 0x0044)
            t.write32(0x40000, val)
        except Exception:
            pass

        t.write32_clr(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)
        t.write32_set(R_AX_PLATFORM_ENABLE, B_AX_PLATFORM_EN)

    def enable_cpu_fwdl(self) -> None:
        """rtw89_mac_enable_cpu_ax: boot_reason 0, dlfw true (the download keeps the CPU off until
        the firmware boots itself). [SRC] mac.c:4165-4205."""
        t = self.t
        if t.read32(R_AX_PLATFORM_ENABLE) & B_AX_WCPU_EN:
            raise BringUpError("fw", "WLAN CPU already enabled")
        t.write32(R_AX_UDM1, 0)
        t.write32(R_AX_UDM2, 0)
        t.write8(R_AX_H2CREG_CTRL_V1, 0)
        t.write8(R_AX_C2HREG_CTRL_V1, 0)
        t.write32(R_AX_HALT_H2C_CTRL, 0)
        t.write32(R_AX_HALT_C2H_CTRL, 0)
        t.write32(R_AX_HALT_H2C, 0)
        t.write32(R_AX_HALT_C2H, 0)
        t.write32_set(R_AX_SYS_CLK_CTRL, B_AX_CPU_CLK_EN)
        val = t.read32(R_AX_WCPU_FW_CTRL)
        val &= ~(B_AX_WCPU_FWDL_EN | B_AX_H2C_PATH_RDY | B_AX_FWDL_PATH_RDY | B_AX_WCPU_FWDL_STS_MASK) & 0xFFFFFFFF
        val |= RTW89_FWDL_INITIAL_STATE << 5
        val |= B_AX_WCPU_FWDL_EN
        t.write32(R_AX_WCPU_FW_CTRL, val)
        t.write16(R_AX_BOOT_REASON, t.read16(R_AX_BOOT_REASON) & ~B_AX_BOOT_REASON_MASK & 0xFFFF)
        t.write32_set(R_AX_PLATFORM_ENABLE, B_AX_WCPU_EN)

    def dmac_pre_init(self) -> None:
        """rtw89_mac_partial_init's pre-download chain: HCI DMA trx enable, DMAC function enables,
        DMAC clock/AXI config, then the USB HCI pre-init. Without the H2C DMA path up, firmware
        packets go out on the wire and the CPU never acks them. [SRC] mac.h:1642,
        mac.c:4213-4270, usb.c:797-822."""
        t = self.t
        t.write32_set(R_AX_HCI_FUNC_EN_V1, B_AX_HCI_TXDMA_EN | B_AX_HCI_RXDMA_EN)

        t.write32(R_AX_DMAC_FUNC_EN,
                  B_AX_MAC_FUNC_EN | B_AX_DMAC_FUNC_EN | B_AX_DISPATCHER_EN |
                  B_AX_PKT_BUF_EN | B_AX_H_AXIDMA_EN)

        t.write32(R_AX_DMAC_CLK_EN, B_AX_DISPATCHER_CLK_EN)
        val = t.read32(R_AX_HAXI_INIT_CFG1)
        val &= ~(B_AX_DMA_MODE_MASK | B_AX_STOP_AXI_MST) & 0xFFFFFFFF
        val |= B_AX_TXHCI_EN_V1 | B_AX_RXHCI_EN_V1 | (DMA_MOD_USB << 18)
        t.write32(R_AX_HAXI_INIT_CFG1, val)
        t.write32_clr(R_AX_HAXI_DMA_STOP1,
                      B_AX_STOP_ACH0 | B_AX_STOP_ACH1 | B_AX_STOP_ACH3 | B_AX_STOP_ACH4 |
                      B_AX_STOP_ACH5 | B_AX_STOP_ACH6 | B_AX_STOP_ACH7 | B_AX_STOP_CH8 |
                      B_AX_STOP_CH9 | B_AX_STOP_CH12 | B_AX_STOP_ACH2 | B_AX_STOP_WPDMA)
        t.write32_clr(R_AX_HAXI_DMA_STOP2, B_AX_STOP_CH10 | B_AX_STOP_CH11)
        t.write32_set(R_AX_PLATFORM_ENABLE, B_AX_AXIDMA_EN)

        # Queue memory: the H2C engine has nothing to drain into without it.
        trx.dle_init(t)
        trx.hfc_init(t)

        # rtw89_usb_ops_mac_pre_init: USBIO mode, clear the RX/TX reset straps, then re-toggle the
        # HCI DMA enables (Realtek's USB IO-hang workaround).
        t.write32_set(R_AX_USB_HOST_REQUEST_2_V1, B_AX_R_USBIO_MODE_V1)
        t.write32_clr(R_AX_USB_WLAN0_1_V1, B_AX_USBRX_RST_V1 | B_AX_USBTX_RST_V1)
        val = t.read32(R_AX_HCI_FUNC_EN_V1)
        val &= ~(B_AX_HCI_RXDMA_EN | B_AX_HCI_TXDMA_EN) & 0xFFFFFFFF
        t.write32(R_AX_HCI_FUNC_EN_V1, val)
        t.write32(R_AX_HCI_FUNC_EN_V1, val | B_AX_HCI_RXDMA_EN | B_AX_HCI_TXDMA_EN)

    def enable_bb_rf(self) -> None:
        """rtw8852c_mac_enable_bb_rf. [SRC] rtw8852c.c:3030-3074."""
        t = self.t
        t.write8_set(R_AX_SYS_FUNC_EN, B_AX_FEN_BBRSTB | B_AX_FEN_BB_GLB_RSTN)
        t.write32_set(R_AX_WLRF_CTRL, B_AX_AFC_AFEDIG)
        t.write32_clr(R_AX_WLRF_CTRL, B_AX_AFC_AFEDIG)
        t.write32_set(R_AX_WLRF_CTRL, B_AX_AFC_AFEDIG)
        t.write32_mask(R_AX_AFE_OFF_CTRL1, B_AX_S0_LDO_VSEL_F_MASK, 0x1)
        t.write32_mask(R_AX_AFE_OFF_CTRL1, B_AX_S1_LDO_VSEL_F_MASK, 0x1)
        for off, val in ((XTAL0, 0x7), (XTAL_SI_ANAPAR_WL, 0x6C),
                         (XTAL_SI_WL_RFC_S0, 0xC7), (XTAL_SI_WL_RFC_S1, 0xC7),
                         (XTAL3, 0xD)):
            t.write_xtal_si(off, val, FULL_BIT_MASK)

    def sys_init(self) -> None:
        """rtw89_mac_sys_init: dmac_func_en_ax + cmac_func_en_ax(0, true).
        [SRC] mac.c:1656-1750, 7111-7130."""
        t = self.t
        t.write32(R_AX_DMAC_FUNC_EN,
                  B_AX_MAC_FUNC_EN | B_AX_DMAC_FUNC_EN |
                  B_AX_MAC_SEC_EN | B_AX_DISPATCHER_EN |
                  B_AX_DLE_CPUIO_EN | B_AX_PKT_IN_EN |
                  B_AX_DMAC_TBL_EN | B_AX_PKT_BUF_EN |
                  B_AX_STA_SCH_EN | B_AX_TXPKT_CTRL_EN |
                  B_AX_WD_RLS_EN | B_AX_MPDU_PROC_EN |
                  B_AX_DMAC_CRPRT | B_AX_H_AXIDMA_EN)
        t.write32(R_AX_DMAC_CLK_EN,
                  B_AX_MAC_SEC_CLK_EN | B_AX_DISPATCHER_CLK_EN |
                  B_AX_DLE_CPUIO_CLK_EN | B_AX_PKT_IN_CLK_EN |
                  B_AX_STA_SCH_CLK_EN | B_AX_TXPKT_CTRL_CLK_EN |
                  B_AX_WD_RLS_CLK_EN | B_AX_BBRPT_CLK_EN)
        t.write32_set(R_AX_CK_EN,
                      B_AX_CMAC_CKEN | B_AX_PHYINTF_CKEN | B_AX_CMAC_DMA_CKEN |
                      B_AX_PTCLTOP_CKEN | B_AX_SCHEDULER_CKEN | B_AX_TMAC_CKEN |
                      B_AX_RMAC_CKEN)
        t.write32_set(R_AX_CMAC_FUNC_EN,
                      B_AX_CMAC_EN | B_AX_CMAC_TXEN | B_AX_CMAC_RXEN |
                      B_AX_PHYINTF_EN | B_AX_CMAC_DMA_EN | B_AX_PTCLTOP_EN |
                      B_AX_SCHEDULER_EN | B_AX_TMAC_EN | B_AX_RMAC_EN |
                      B_AX_CMAC_CRPRT)

    def trx_init(self) -> None:
        """rtw89_mac_trx_init on the SCC profile. [SRC] mac.c:4040-4080."""
        trx.trx_init(self.t)

    def mac_post_init(self) -> None:
        """rtw89_usb_ops_mac_post_init for RTL8852C.
        [SRC] usb.c:886-922."""
        t = self.t
        t.write32_clr(R_AX_USB3_MAC_NPI_CONFIG_INTF_0_V1, B_AX_SSPHY_LFPS_FILTER_V1)
        bulksize = USB3_BULKSIZE if trx.is_usb3(t) else USB2_BULKSIZE
        t.write8(R_AX_RXDMA_SETTING, bulksize)
        for ep in range(5, 13):
            if ep == 8:
                continue
            t.write8_mask(R_AX_USB_ENDPOINT_0_V1, B_AX_EP_IDX_V1, ep)
            t.write8(R_AX_USB_ENDPOINT_2_NUMP_V1, NUMP)
        # rtw89_usb_rx_agg_cfg_v2
        t.write32(R_AX_RXAGG_0_V1,
                  B_AX_RXAGG_0_EN |
                  (255 << 16) | (32 << 8) | 20)
        t.write32(R_AX_RXAGG_1_V1, 0x1F)

    def setup_phycap(self) -> dict:
        """rtw89_mac_setup_phycap_part0: ask the running firmware for the PHY capability through
        the H2CREG/C2HREG mailbox. AX chips return after part0. [SRC] mac.c:3222-3341,
        fw.c:9297-9325."""
        # AX: content_len = 0 and part 0 packs into w0 bits 23:16. [SRC] mac.c:3189-3200
        c2h = firmware.msg_reg(self.t, RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE,
                               words=[0], content_len=0)
        if c2h["id"] != RTW89_FWCMD_C2HREG_FUNC_PHY_CAP:
            raise BringUpError(
                "phycap", f"firmware returned C2H id 0x{c2h['id']:x}, expected PHY_CAP")
        w = c2h["words"]
        tx_nss = w[1] & RTW89_C2HREG_PHYCAP_W1_TX_NSS
        rx_nss = (w[0] & RTW89_C2HREG_PHYCAP_W0_RX_NSS) >> 16
        protocol = (w[1] & RTW89_C2HREG_PHYCAP_W1_PROT) >> 8
        tx_ant = (w[3] & RTW89_C2HREG_PHYCAP_W3_ANT_TX_NUM) >> 8
        rx_ant = (w[3] & RTW89_C2HREG_PHYCAP_W3_ANT_RX_NUM) >> 16

        hal = {
            "tx_nss": min(tx_nss, RTW89_8852C_TX_NSS) if tx_nss
                      else RTW89_8852C_TX_NSS,
            "rx_nss": min(rx_nss, RTW89_8852C_RX_NSS) if rx_nss
                      else RTW89_8852C_RX_NSS,
            "antenna_tx": 0,
            "antenna_rx": 0,
            "tx_path_diversity": False,
            "protocol": protocol,
            "no_eht": protocol < RTW89_C2HREG_PHYCAP_W1_PROT_11BE,
            "tx_nss_raw": tx_nss,
            "rx_nss_raw": rx_nss,
            "tx_ant": tx_ant,
            "rx_ant": rx_ant,
        }
        if tx_ant == 1:
            hal["antenna_tx"] = RF_B
        if rx_ant == 1:
            hal["antenna_rx"] = RF_B
        if tx_nss == 1 and tx_ant == 2 and rx_ant == 2:
            hal["antenna_tx"] = RF_B
            hal["tx_path_diversity"] = True
        return hal

    def port_update(self) -> None:
        """rtw89_mac_port_update for monitor vif (net_type NO_LINK, port 0). [SRC] mac.c:5109."""
        t = self.t
        t.read32(0xC400)                             # R_AX_PORT_CFG_P0
        t.write32_clr(0xC400, 1 << 1)               # B_AX_TXBCN_RPT_EN
        t.write32_clr(0xC400, 1 << 0)               # B_AX_RXBCN_RPT_EN
        t.write32_mask(0xC400, 0xC00, 0)            # B_AX_NET_TYPE_MASK = 0 (NO_LINK)
        t.write32_clr(0xC400, (1 << 13) | (1 << 16) | B_AX_BCN_DROP_ALLOW)
        t.write32_clr(0xC400, 1 << 4)               # B_AX_RX_BSSID_FIT_EN
        t.write32_clr(0xC400, 1 << 3)               # B_AX_TSF_UDT_EN
        t.write32_clr(0xC400, 1 << 12)              # B_AX_BCNTX_EN
        t.write32_mask(0xC414, 0xFFFF, 100)         # R_AX_BCN_SPACE_CFG_P0 = BCN_INTERVAL (100)
        t.write8(R_AX_P0MB_HGQ_WINDOW_CFG_0, 0)     # 0xC590
        t.write8_set(R_AX_MD_TSFT_STMP_CTL, 0x3)    # 0xCA08: B_AX_UPD_HGQMD | B_AX_UPD_TIMIE
        t.write16_mask(0xC418, 0xFF, 0)             # R_AX_DTIM_CTRL_P0
        t.write32_clr(R_AX_MBSSID_DROP_0, 0x10001)  # 0xC63C
        t.write32_mask(0xC404, 0xFF, 0x20)          # R_AX_TBTT_PROHIB_P0 SETUP
        t.write32_mask(0xC404, 0x0FFF0000, 0x10)    # R_AX_TBTT_PROHIB_P0 HOLD
        t.write32_mask(0xC408, 0x0FFF0000, 0x20)    # R_AX_BCN_AREA_P0 MASK
        t.write16_mask(0xC40E, 0x0FFF, 0x10)        # R_AX_TBTTERLYINT_CFG_P0
        t.write16_mask(0xC412, 0xFF00, 0x04)        # R_AX_TBTT_AGG_P0
        t.write32_mask(R_AX_PTCL_BSS_COLOR_0, 0x3F, 0) # 0xC6A0
        t.write32_clr(R_AX_MBSSID_CTRL, 0xFFFFFFFF) # 0xC568
        t.write32_set(0xC400, 1 << 2)               # B_AX_PORT_FUNC_EN
        t.write32_mask(0xC40C, 0x0FFF, 0x10)        # R_AX_BCNERLYINT_CFG_P0
        t.write32_mask(0xC438, 0xFF, 0)             # R_AX_BCN_PSR_RPT_P0

        self.dmac_tbl_init(0)
        self.cmac_tbl_init(0)

    def dmac_tbl_init(self, macid: int = 0) -> None:
        """rtw89_mac_dmac_tbl_init. [SRC] mac.c:4413-4421."""
        t = self.t
        for i in range(4):
            t.write32(R_AX_FILTER_MODEL_ADDR,
                      DMAC_TBL_BASE_ADDR + (macid << 4) + (i << 2))
            t.write32(R_AX_INDIR_ACCESS_ENTRY, 0)

    def cmac_tbl_init(self, macid: int = 0) -> None:
        """rtw89_mac_cmac_tbl_init. [SRC] mac.c:4423-4435."""
        t = self.t
        t.write32(R_AX_FILTER_MODEL_ADDR,
                  CMAC_TBL_BASE_ADDR + macid * CCTL_INFO_SIZE)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 0, 0x00000004)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 4, 0x400A0004)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 8, 0)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 12, 0)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 16, 0)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 20, 0x0E43000B)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 24, 0)
        t.write32(R_AX_INDIR_ACCESS_ENTRY + 28, 0x000B8109)

    def config_monitor(self) -> None:
        """Route all RX frames (Management, Control, Data) to host in promiscuous mode.
        [SRC] mac.c:2673 (fltr opt), mac80211.c:320-390 (promisc filter), reg.h:3355-3363."""
        t = self.t
        # Forward MGNT, CTRL, DATA frames to host (0x55555555)
        t.write32(R_AX_CTRL_FLTR, RX_FLTR_FRAME_TO_HOST)  # 0xCE24
        t.write32(R_AX_MGNT_FLTR, RX_FLTR_FRAME_TO_HOST)  # 0xCE28
        t.write32(R_AX_DATA_FLTR, RX_FLTR_FRAME_TO_HOST)  # 0xCE2C

        # Promiscuous / sniffer mode: sniffer bit ON, no A1/CAM/BSSID match required,
        # preserve MPDU max length bits (21:16) [SRC] mac80211.c:371, mac.c:2688
        t.write32_mask(R_AX_RX_FLTR_OPT, B_AX_RX_FLTR_CFG_MASK, SNIFFER_AX_RX_FLTR)

        # Ensure RCR has channel enable bit set and STOP_RX_IN cleared [SRC] mac.c:2954, reg.h:3305
        t.write16_clr(R_AX_RCR, B_AX_STOP_RX_IN)
        t.write8_mask(R_AX_RCR, B_AX_CH_EN_MASK, 0x1)

        # Enable PPDU status reports to host [SRC] mac.c:6313-6318
        t.write32(R_AX_PPDU_STAT, 0x2B)
        t.write32_mask(R_AX_HW_RPT_FWD, 0x3, 1)

