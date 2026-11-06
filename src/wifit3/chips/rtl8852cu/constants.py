"""RTL8852CU (rtw89 8852C over USB) register-access constants, ported from the mainline
rtw89 tree (torvalds/linux master, post-6.18; USB support post-v6.18).
Values are pasted verbatim from the source; each carries its file:line.
"""

# Band & Bandwidth definitions. [SRC] core.h:400-420.
RTW89_BAND_2G = 0                # enum rtw89_band
RTW89_BAND_5G = 1
RTW89_BAND_6G = 2
RTW89_CHANNEL_WIDTH_20 = 0       # enum rtw89_bandwidth
RTW89_CHANNEL_WIDTH_40 = 1
RTW89_CHANNEL_WIDTH_80 = 2
RTW89_CHANNEL_WIDTH_160 = 3

# WMAC channel setting registers. [SRC] reg.h:2170-2596.
R_AX_WMAC_RFMOD = 0xC010
B_AX_WMAC_RFMOD_MASK = 0x3
AX_WMAC_RFMOD_20M = 0
AX_WMAC_RFMOD_40M = 1
AX_WMAC_RFMOD_80M = 2
AX_WMAC_RFMOD_160M = 3
R_AX_TX_SUB_CARRIER_VALUE = 0xC088
R_AX_TXRATE_CHK = 0xC628
B_AX_BAND_MODE = 1 << 4
B_AX_RTS_LIMIT_IN_OFDM6 = 1 << 1
B_AX_CHECK_CCK_EN = 1 << 0

# USB vendor control transfer (rtw89_usb_vendorreq). [SRC] usb.h:10-12
RTW89_USB_VENQT = 0x05           # bRequest for register access
RTW89_USB_VENQT_READ = 0xc0      # bmRequestType: vendor + device-to-host (IN)
RTW89_USB_VENQT_WRITE = 0x40     # bmRequestType: vendor + host-to-device (OUT)

RTW89_USB_VENDORREQ_ATTEMPTS = 10     # retry budget per op. [SRC] usb.c:34
RTW89_USB_VENDORREQ_TIMEOUT_MS = 500  # [SRC] usb.c:47

# CMAC register window. A read here can return R32_DEAD until its clock is on, so
# rtw89_usb_read_cmac re-enables the clock and re-reads. [SRC] mac.h:578-579, reg.h.
R_AX_CMAC_REG_START = 0xC000     # [SRC] reg.h:2110
R_AX_CMAC_REG_END = 0xFFFF       # [SRC] reg.h:3738
RTW89_R32_DEAD = 0xDEADBEEF      # [SRC] mac.h:578
MAC_REG_POOL_COUNT = 10          # read_cmac retry budget. [SRC] mac.h:579
R_AX_CK_EN = 0xC004              # [SRC] reg.h:2126
B_AX_CMAC_ALLCKEN = 0xFFFFFFFF   # GENMASK(31, 0). [SRC] reg.h:2128

# rtw8852c_usb_info: the V1 (8852C) USB register block. [SRC] rtw8852cu.c:10-16, reg.h:476-498.
R_AX_USB_HOST_REQUEST_2_V1 = 0x5078          # + B_AX_R_USBIO_MODE_V1 BIT(4). reg.h:479,480
R_AX_USB_WLAN0_1_V1 = 0x5174                 # + USBRX/USBTX_RST_V1 bits 9/8. reg.h:483-485
R_AX_HCI_FUNC_EN_V1 = 0x7880                 # + HCI_RXDMA_EN BIT(1), HCI_TXDMA_EN BIT(0). reg.h:498
R_AX_USB3_MAC_NPI_CONFIG_INTF_0_V1 = 0x5114  # + SSPHY_LFPS_FILTER_V1 BIT(31). reg.h:481,482
R_AX_USB_ENDPOINT_0_V1 = 0x5060              # + EP_IDX_V1 GENMASK(3, 0). reg.h:476,477
R_AX_USB_ENDPOINT_2_V1 = 0x5068              # reg.h:478

# The 8852C answers at the V1 addresses; mac_be.c selects by chip_id. [SRC] usb.c
# rtw89_usb_ops_mac_lv1_rcvy: RTL8852C -> _V1 reg+mask. reg.h:476-498.
B_AX_USBRX_RST_V1 = 1 << 9       # reg.h:484
B_AX_USBTX_RST_V1 = 1 << 8       # reg.h:485
B_AX_R_USBIO_MODE_V1 = 1 << 4    # reg.h:480
B_AX_HCI_RXDMA_EN = 1 << 1       # reg.h:527
B_AX_HCI_TXDMA_EN = 1 << 0       # reg.h:528
B_AX_SSPHY_LFPS_FILTER_V1 = 1 << 31  # reg.h:482
B_AX_EP_IDX_V1 = 0xF             # GENMASK(3, 0). reg.h:477

# rtw89_usb_ops_mac_post_init RXDMA/NUMP. [SRC] usb.c, reg.h:1053-1057.
R_AX_RXDMA_SETTING = 0x8908      # reg.h:1053
USB11_BULKSIZE = 0x2             # reg.h:1055
USB2_BULKSIZE = 0x1              # reg.h:1056
USB3_BULKSIZE = 0x0              # reg.h:1057
NUMP = 0x1                       # reg.h:388
# USB_SPEED_SUPER from the USB spec: pyusb's Device.speed is 1=low, 2=full, 3=high, 4=super,
# 5=super+. usb.c:1293-1296 branches on udev->speed == USB_SPEED_SUPER to pick the DLE row set.
USB_SPEED_SUPER = 4

# rtw89_read_chip_ver: chip version. [SRC] core.c:5939-5953.
R_AX_SYS_CFG1 = 0x00F0           # reg.h:181
B_AX_CHIP_VER_MASK = 0xF000      # GENMASK(15, 12). reg.h:182

# rtw89_mac_power_switch (mac.c:1458-1521).
PWR_ACT = 1                      # mac.c:1463
R_AX_IC_PWR_STATE = 0x03F0       # reg.h:313
B_AX_WLMAC_PWR_STE_MASK = 0x300  # GENMASK(9, 8). reg.h:315
R_AX_SCOREBOARD = 0x00AC         # reg.h:155
MAC_AX_NOTIFY_TP_MAJOR = 0x81    # reg.h:160
MAC_AX_NOTIFY_PWR_MAJOR = 0x80   # reg.h:161

# rtw89_mac_power_switch_boot_mode (USB only). [SRC] mac.c:1444-1456.
R_AX_GPIO_MUXCFG = 0x0040        # reg.h:81
B_AX_BOOT_MODE = 1 << 19         # reg.h:82
B_AX_AUTO_WLPON = 1 << 10        # reg.h:186
R_AX_RSV_CTRL = 0x001C           # reg.h:47
B_AX_R_DIS_PRST = 1 << 6         # reg.h:48

# rtw8852c_pwr_on_func. [SRC] rtw8852c.c:211-331, reg.h.
R_AX_SYS_STATUS1 = 0x00F4                    # reg.h:184
B_AX_PAD_HCI_SEL_V2_MASK = 0x38              # GENMASK(5, 3). reg.h:187
MAC_AX_HCI_SEL_PCIE_USB = 3                  # reg.h:191
R_AX_LDO_AON_CTRL0 = 0x0218                  # reg.h:246
B_AX_PD_REGU_L = 1 << 16                     # reg.h:247
R_AX_SYS_PW_CTRL = 0x0004                    # reg.h:21
B_AX_AFSM_WLSUS_EN = 1 << 11                 # reg.h:32
B_AX_AFSM_PCIE_SUS_EN = 1 << 12              # reg.h:31
B_AX_DIS_WLBT_PDNSUSEN_SOPC = 1 << 18        # reg.h:26
B_AX_APDM_HPDN = 1 << 15                     # reg.h:29
B_AX_APFM_SWLPS = 1 << 10                    # reg.h:33
B_AX_RDY_SYSPWR = 1 << 17                    # reg.h:27
B_AX_EN_WLON = 1 << 16                       # reg.h:28
B_AX_APFN_ONMAC = 1 << 8                     # reg.h:35
R_AX_WLLPS_CTRL = 0x0090                     # reg.h:149
B_AX_DIS_WLBT_LPSEN_LOPC = 1 << 1            # reg.h:152
R_AX_SPS_DIG_ON_CTRL0 = 0x0200               # reg.h:237
B_AX_OCP_L1_MASK = 0xE000                    # GENMASK(15, 13). reg.h:240
R_AX_PLATFORM_ENABLE = 0x0088                # reg.h:143
B_AX_PLATFORM_EN = 1 << 0                    # reg.h:147
R_AX_SYS_SDIO_CTRL = 0x0070                  # reg.h:120
B_AX_PCIE_CALIB_EN_V1 = 1 << 12              # reg.h:77
R_AX_SYS_ISO_CTRL_EXTEND = 0x0080            # reg.h:2104
B_AX_CMAC1_FEN = 1 << 30                     # reg.h:2105
B_AX_R_SYM_ISO_CMAC12PP = 1 << 5             # reg.h:2108
R_AX_AFE_CTRL1 = 0x0024                      # reg.h:2096
B_AX_R_SYM_WLCMAC1_P4_PC_EN = 1 << 4         # reg.h:2098
B_AX_R_SYM_WLCMAC1_P3_PC_EN = 1 << 3         # reg.h:2099
B_AX_R_SYM_WLCMAC1_P2_PC_EN = 1 << 2         # reg.h:2100
B_AX_R_SYM_WLCMAC1_P1_PC_EN = 1 << 1         # reg.h:2101
B_AX_R_SYM_WLCMAC1_PC_EN = 1 << 0            # reg.h:2102
R_AX_SYS_ADIE_PAD_PWR_CTRL = 0x0018          # reg.h:43
B_AX_SYM_PADPDN_WL_PTA_1P3 = 1 << 6          # reg.h:44
B_AX_SYM_PADPDN_WL_RFC_1P3 = 1 << 5          # reg.h:45
R_AX_PMC_DBG_CTRL2 = 0x00CC                  # reg.h:166
B_AX_SYSON_DIS_PMCR_AX_WRMSK = 1 << 2        # reg.h:167
R_AX_SYS_ISO_CTRL = 0x0000                   # reg.h:11
B_AX_ISO_EB2CORE = 1 << 8                    # reg.h:15
B_AX_PWC_EV2EF_B15 = 1 << 15                 # reg.h:13
B_AX_PWC_EV2EF_B14 = 1 << 14                 # reg.h:14
R_AX_GPIO0_15_EECS_EESK_LED1_PULL_LOW_EN = 0x02E4  # reg.h:297
B_AX_LED1_PULL_LOW_EN = 1 << 18              # reg.h:298
B_AX_EESK_PULL_LOW_EN = 1 << 17              # reg.h:299
B_AX_EECS_PULL_LOW_EN = 1 << 16              # reg.h:300
R_AX_DMAC_FUNC_EN = 0x8400                   # reg.h:532
B_AX_MAC_FUNC_EN = 1 << 30                   # reg.h:534
B_AX_DMAC_FUNC_EN = 1 << 29                  # reg.h:535
B_AX_MPDU_PROC_EN = 1 << 28                  # reg.h:536
B_AX_WD_RLS_EN = 1 << 27                     # reg.h:537
B_AX_DLE_WDE_EN = 1 << 26                    # reg.h:538
B_AX_TXPKT_CTRL_EN = 1 << 25                 # reg.h:539
B_AX_STA_SCH_EN = 1 << 24                    # reg.h:540
B_AX_DLE_PLE_EN = 1 << 23                    # reg.h:541
B_AX_PKT_BUF_EN = 1 << 22                    # reg.h:542
B_AX_DMAC_TBL_EN = 1 << 21                   # reg.h:543
B_AX_PKT_IN_EN = 1 << 20                     # reg.h:544
B_AX_DLE_CPUIO_EN = 1 << 19                  # reg.h:545
B_AX_DISPATCHER_EN = 1 << 18                 # reg.h:546
B_AX_BBRPT_EN = 1 << 17                      # reg.h:547
B_AX_MAC_SEC_EN = 1 << 16                    # reg.h:548
B_AX_MAC_UN_EN = 1 << 15                     # reg.h:550
B_AX_H_AXIDMA_EN = 1 << 14                   # reg.h:551
R_AX_CMAC_FUNC_EN = 0xC000                   # reg.h:2112
B_AX_CMAC_EN = 1 << 30                       # reg.h:2115
B_AX_CMAC_TXEN = 1 << 29                     # reg.h:2116
B_AX_CMAC_RXEN = 1 << 28                     # reg.h:2117
B_AX_FORCE_CMACREG_GCKEN = 1 << 15           # reg.h:2118
B_AX_PHYINTF_EN = 1 << 5                     # reg.h:2119
B_AX_CMAC_DMA_EN = 1 << 4                    # reg.h:2120
B_AX_PTCLTOP_EN = 1 << 3                     # reg.h:2121
B_AX_SCHEDULER_EN = 1 << 2                   # reg.h:2122
B_AX_TMAC_EN = 1 << 1                        # reg.h:2123
B_AX_RMAC_EN = 1 << 0                        # reg.h:2124
R_AX_LED1_FUNC_SEL = 0x02DC                  # reg.h:293
B_AX_PINMUX_EESK_FUNC_SEL_V1_MASK = 0xF000000  # GENMASK(27, 24). reg.h:294
PINMUX_EESK_FUNC_SEL_BT_LOG = 0x1            # reg.h:295

# rtw89_mac_write_xtal_si_be / read_xtal_si_be. [SRC] mac_be.c:413-467, reg.h:4423-4429.
R_BE_WLAN_XTAL_SI_CTRL = 0x0270
B_BE_WL_XTAL_SI_CMD_POLL = 1 << 31
B_BE_WL_XTAL_SI_CHIPID_MASK = 0x70000000     # GENMASK(30, 28)
B_BE_WL_XTAL_SI_MODE_MASK = 0x03000000       # GENMASK(25, 24)
B_BE_WL_XTAL_SI_BITMASK_MASK = 0x00FF0000    # GENMASK(23, 16)
B_BE_WL_XTAL_SI_DATA_MASK = 0x0000FF00       # GENMASK(15, 8)
B_BE_WL_XTAL_SI_ADDR_MASK = 0x000000FF       # GENMASK(7, 0)
XTAL_SI_NORMAL_WRITE = 0x00                  # reg.h:260
XTAL_SI_NORMAL_READ = 0x01                   # reg.h:261

# enum rtw89_mac_xtal_si_offset. [SRC] mac.h:1498-1541.
XTAL_SI_XTAL_XMD_2 = 0x24
XTAL_SI_LDO_LPS = 0x70                       # GENMASK(6, 4)
XTAL_SI_XTAL_XMD_4 = 0x26
XTAL_SI_LPS_CAP = 0x0F                       # GENMASK(3, 0)
XTAL_SI_SRAM2RFC = 0x80                      # BIT(7)
XTAL_SI_GND_SHDN_WL = 0x40                   # BIT(6)
XTAL_SI_SHDN_WL = 0x20                       # BIT(5)
XTAL_SI_RFC2RF = 0x10                        # BIT(4)
XTAL_SI_OFF_EI = 0x08                        # BIT(3)
XTAL_SI_OFF_WEI = 0x04                       # BIT(2)
XTAL_SI_PON_EI = 0x02                        # BIT(1)
XTAL_SI_PON_WEI = 0x01                       # BIT(0)
XTAL_SI_ANAPAR_WL = 0x90
XTAL_SI_WL_RFC_S0 = 0x80                     # mac.h:1527
XTAL_SI_RF00 = 0x01                          # BIT(0). mac.h:1529
XTAL_SI_WL_RFC_S1 = 0x81                     # mac.h:1530
XTAL_SI_RF10 = 0x01                          # BIT(0). mac.h:1532

# rtw8852c_pwr_off_func. [SRC] rtw8852c.c:332-397, reg.h.
B_AX_APFM_OFFMAC = 1 << 9                    # reg.h:34
SW_LPS_OPTION = 0x0001A0B2                   # reg.h:153
B_AX_XTAL_OFF_A_DIE = 1 << 22                # reg.h:25
R_AX_WLRF_CTRL = 0x02F0                      # reg.h:306
B_AX_AFC_AFEDIG = 1 << 17                    # reg.h:307
R_AX_SYS_FUNC_EN = 0x0002                    # reg.h:17
B_AX_FEN_BB_GLB_RSTN = 1 << 1                # reg.h:18
B_AX_FEN_BBRSTB = 1 << 0                     # reg.h:19
B_AX_R_SYM_FEN_WLBBGLB_1 = 1 << 17           # reg.h:2106
B_AX_R_SYM_FEN_WLBBFUN_1 = 1 << 16           # reg.h:2107
R_AX_SYS_SWR_CTRL1 = 0x0010                  # reg.h:40
B_AX_SYM_CTRL_SPS_PWMFREQ = 1 << 10          # reg.h:41
B_AX_REG_ZCDC_H_MASK = 0x60000               # GENMASK(18, 17). reg.h:239

# rtw89_usb_info for the 8852C: DMA channel -> bulkout id. [SRC] rtw8852cu.c:17-27.
BULKOUT_ID_ACH0 = 3
BULKOUT_ID_ACH2 = 5
BULKOUT_ID_ACH4 = 4
BULKOUT_ID_ACH6 = 6
BULKOUT_ID_B0MG = 0
BULKOUT_ID_B0HI = 0
BULKOUT_ID_B1MG = 1
BULKOUT_ID_B1HI = 1
BULKOUT_ID_H2C = 2
RX_AGG_ALIGNMENT = 8

# DMA / TX channel enums. [SRC] core.h:3812-3824, txrx.h:645.
RTW89_DMA_H2C = 12
RTW89_TXCH_CH12 = 12                          # FW CMD
RTW89_USB_RECVBUF_SZ = 20480                  # usb.h:16
RTW89_USB_RXCB_NUM = 8                        # usb.h:17
RTW89_USB_RX_SKB_NUM = 16                     # usb.h:18
RTW89_USB_MAX_RXQ_LEN = 512                   # usb.h:19
RTW89_USB_MOD512_PADDING = 4                  # usb.h:20
RTW89_MAX_ENDPOINT_NUM = 9                    # usb.h:22
RTW89_MAX_BULKOUT_NUM = 7                     # usb.h:23

# --- M2: firmware download (fw.c, mac.c, core.c, txrx.h) ------------------------------------------
# WLAN-CPU fwdl control/status. [SRC] reg.h:37-38, 146, 210-222, 237-250.
R_AX_SYS_CLK_CTRL = 0x0008                    # reg.h:37
B_AX_CPU_CLK_EN = 1 << 14                     # reg.h:38
B_AX_WCPU_EN = 1 << 1                         # reg.h:146
R_AX_HALT_H2C_CTRL = 0x0160                   # reg.h:210
R_AX_HALT_C2H_CTRL = 0x0164                   # reg.h:213
R_AX_HALT_H2C = 0x0168                        # reg.h:211
R_AX_HALT_C2H = 0x016C                        # reg.h:214
R_AX_WCPU_FW_CTRL = 0x01E0                    # reg.h:216
B_AX_WCPU_FWDL_STS_MASK = 0xE0                # GENMASK(7, 5). reg.h:219
B_AX_FWDL_PATH_RDY = 1 << 2                   # reg.h:220
B_AX_H2C_PATH_RDY = 1 << 1                    # reg.h:221
B_AX_WCPU_FWDL_EN = 1 << 0                    # reg.h:222
R_AX_BOOT_REASON = 0x01E6                     # reg.h:237
B_AX_BOOT_REASON_MASK = 0x7                   # GENMASK(2, 0). reg.h:238
R_AX_UDM1 = 0x01F4                            # reg.h:244
R_AX_UDM2 = 0x01F8                            # reg.h:250

# rtw89_fwdl_check_path_ready_ax / rtw89_fw_get_rdy_ax / rtw89_fw_check_rdy. [SRC] mac.c:7428, 106.
FWDL_WAIT_CNT = 400_000                       # fw.h:5358 (1us poll budget)
FWDL_WAIT_CNT_USB = 3_200                     # fw.h:5359
RTW89_FWDL_INITIAL_STATE = 0                  # fw.h:11
RTW89_FWDL_WCPU_FW_INIT_RDY = 7               # fw.h:18

# fwcmd TX descriptor = struct rtw89_rxdesc_short (16 bytes), dword0 only. [SRC] core.h:1360,
# core.c:1896-1917, txrx.h:345,350, rtw8852c.c:3229 (h2c_desc_size).
H2C_DESC_SIZE = 16
AX_RXD_RPKT_LEN_MASK = 0x3FFF                 # GENMASK(13, 0). txrx.h:345
AX_RXD_RPKT_TYPE_SHIFT = 24                   # GENMASK(27, 24). txrx.h:350
RTW89_CORE_RX_TYPE_H2C = 13                   # core.h:411
RTW89_CORE_RX_TYPE_FWDL = 14                  # core.h:412

# H2C command header (struct fwcmd_hdr, 8 bytes). [SRC] fw.h:4599-4617, 4677-4741.
H2C_HEADER_LEN = 8
H2C_HDR_CAT_MAC = 0x1                         # fw.h:4691
H2C_CL_MAC_FWDL = 0x3                         # fw.h:4740
H2C_FUNC_MAC_FWHDR_DL = 0x0                   # fw.h:4741
H2C_HDR_CLASS_SHIFT = 2                       # GENMASK(7, 2). fw.h:4601
H2C_HDR_TOTAL_LEN_MASK = 0x3FFF               # GENMASK(13, 0). fw.h:4679

# Multi-firmware container + v1 suite header. [SRC] fw.h:4293, fw.c:404-537.
RTW89_MFW_SIG = 0xFF                          # fw.h:4293
RTW89_FW_NORMAL = 1                           # enum rtw89_fw_type. fw.h
FW_HDR_V1_W5_HDR_SIZE_SHIFT = 16              # GENMASK(31, 16)
FW_HDR_V1_W6_SEC_NUM_SHIFT = 8                # GENMASK(15, 8)
FW_HDR_V1_W6_SEC_NUM_MASK = 0xFF00
FW_HDR_V1_W6_DSP_CHKSUM = 1 << 24
FW_HDR_V1_W7_PART_SIZE_MASK = 0xFFFF          # GENMASK(15, 0)
FW_HDR_V1_W7_DYN_HDR = 1 << 16
FWSECTION_HDR_V1_W1_SEC_SIZE_MASK = 0xFFFFFF  # GENMASK(23, 0)
FWSECTION_HDR_V1_W1_SECTIONTYPE_SHIFT = 24    # GENMASK(27, 24)
FWSECTION_HDR_V1_W1_CHECKSUM = 1 << 28
FWSECTION_HDR_V1_W2_MSSC_MASK = 0xFF          # GENMASK(7, 0)
FWDL_SECURITY_SECTION_TYPE = 9
FWDL_SECTION_CHKSUM_LEN = 8
FWDL_SECURITY_SIGLEN = 512
FWDL_SECURITY_CHKSUM_LEN = 8
FWDL_MSS_POOL_DEFKEYSETS_SIZE = 8
FORMATTED_MSSC = 0xFF
MSS_POOL_HDR_LEN = 32                         # sizeof(rtw89_fw_mss_pool_hdr) without rmp_tbl[]
MSS_SIGNATURE = b"MSSKPOOL"                   # fw.c:41
FW_ASSET = "rtw8852c_fw.bin"                  # rtw89/rtw8852c_fw.bin, mfw container

# v0 suite header (struct rtw89_fw_hdr, sections at offset 32). [SRC] fw.h:605-633, fw.c:140-270.
FW_HDR_VER_W1_SHIFT = 0
FW_HDR_W1_MAJOR_MASK = 0xFF
FW_HDR_W1_MINOR_SHIFT = 8
FW_HDR_W1_SUBVERSION_SHIFT = 16
FW_HDR_W1_SUBINDEX_SHIFT = 24
FW_HDR_W3_LEN_SHIFT = 16                      # GENMASK(23, 16)
FW_HDR_W3_LEN_MASK = 0xFF
FWSECTION_HDR_W2_MSSC_MASK_V0 = 0xFFFFFFFF     # v0 takes the whole word. fw.h:603
FWDL_SECTION_PER_PKT_LEN = 2020               # AX part_size, forced by the parser. fw.c:164

# --- M2: USB HCI/DMA bring-up before a bulk transfer can work (rtw89_mac_partial_init's pre-init
# chain: ctrl_hci_dma_trx -> hci_func_en -> dmac_func_pre_en -> usb mac_pre_init). ---------------
# [SRC] mac.h:1642, mac.c:4213-4262, usb.c:797-822, reg.h.
R_AX_DMAC_CLK_EN = 0x8404                     # reg.h:574
B_AX_DISPATCHER_CLK_EN = 1 << 18              # reg.h:582
R_AX_HAXI_INIT_CFG1 = 0x1000                  # reg.h:359
B_AX_DMA_MODE_MASK = 0xC0000                  # GENMASK(19, 18). reg.h:362
B_AX_STOP_AXI_MST = 1 << 17                   # reg.h:367
B_AX_RXHCI_EN_V1 = 1 << 15                    # reg.h:369
B_AX_TXHCI_EN_V1 = 1 << 7                     # reg.h:372
DMA_MOD_USB = 0x2                             # reg.h:365
B_AX_AXIDMA_EN = 1 << 3                       # reg.h:144
R_AX_HAXI_DMA_STOP1 = 0x1010                  # reg.h:377
B_AX_STOP_WPDMA = 1 << 19                      # reg.h:378
B_AX_STOP_CH12 = 1 << 18                      # reg.h:379
B_AX_STOP_CH9 = 1 << 17                       # reg.h:380
B_AX_STOP_CH8 = 1 << 16                       # reg.h:381
B_AX_STOP_ACH7 = 1 << 15
B_AX_STOP_ACH6 = 1 << 14
B_AX_STOP_ACH5 = 1 << 13
B_AX_STOP_ACH4 = 1 << 12
B_AX_STOP_ACH3 = 1 << 11
B_AX_STOP_ACH2 = 1 << 10                      # reg.h:387
B_AX_STOP_ACH1 = 1 << 9
B_AX_STOP_ACH0 = 1 << 8                       # reg.h:389
R_AX_HAXI_DMA_STOP2 = 0x11C0                  # reg.h:425
B_AX_STOP_CH11 = 1 << 1                       # reg.h:426
B_AX_STOP_CH10 = 1 << 0                       # reg.h:427

# --- M2: DLE/HFC (TX/RX queue) setup, DLFW quota profile, USB2/USB3 share it. [SRC] mac.c:1194,
# 2274-2360; mac.h:597-625; reg.h:458-1599; rtw8852c.c:96-127. -------------------------------
R_AX_DMAC_CLK_EN_WDE = 1 << 26                # B_AX_DLE_WDE_CLK_EN. reg.h:576
B_AX_DLE_PLE_CLK_EN = 1 << 23                 # reg.h:579
R_AX_WDE_PKTBUF_CFG = 0x8C08                  # reg.h:1159
B_AX_WDE_PAGE_SEL_MASK = 0x3                  # GENMASK(1, 0). reg.h:1161
B_AX_WDE_START_BOUND_MASK = 0x3F00            # GENMASK(13, 8). reg.h:1160
B_AX_WDE_FREE_PAGE_NUM_MASK = 0x1FFF0000      # GENMASK(28, 16). reg.h:1162
R_AX_PLE_PKTBUF_CFG = 0x9008                  # reg.h:1399
B_AX_PLE_PAGE_SEL_MASK = 0x3                  # GENMASK(1, 0). reg.h:1401
B_AX_PLE_START_BOUND_MASK = 0x3F00            # GENMASK(13, 8). reg.h:1400
B_AX_PLE_FREE_PAGE_NUM_MASK = 0x1FFF0000      # GENMASK(28, 16). reg.h:1402
S_AX_WDE_PAGE_SEL_64 = 0                      # mac.h:605
S_AX_PLE_PAGE_SEL_128 = 1                     # mac.h:614
DLE_BOUND_UNIT = 8 * 1024                     # mac.h:597
R_AX_WDE_INI_STATUS = 0x8D00                  # reg.h:1388
WDE_MGN_INI_RDY = (1 << 1) | (1 << 0)         # reg.h:1389-1391
R_AX_PLE_INI_STATUS = 0x9100                  # reg.h:1596
PLE_MGN_INI_RDY = (1 << 1) | (1 << 0)         # reg.h:1597-1599
R_AX_WDE_QTA0_CFG = 0x8C40                    # reg.h:1375 (stride 4)
R_AX_PLE_QTA0_CFG = 0x9040                    # reg.h:1579 (stride 4, 12 slots)
B_AX_WDE_MIN_SIZE_MASK = 0xFFF                # GENMASK(11, 0). reg.h:1374
B_AX_WDE_MAX_SIZE_MASK = 0xFFF0000            # GENMASK(27, 16). reg.h:1373
B_AX_PLE_MIN_SIZE_MASK = 0xFFF                # GENMASK(11, 0). reg.h:1578
B_AX_PLE_MAX_SIZE_MASK = 0xFFF0000            # GENMASK(27, 16). reg.h:1577
R_AX_HCI_FC_CTRL_V1 = 0x1700                  # reg.h:458
R_AX_CH_PAGE_CTRL_V1 = 0x1704                 # reg.h:459
B_AX_HCI_FC_EN = 1 << 0                       # reg.h:1093
B_AX_HCI_FC_CH12_EN = 1 << 3                  # reg.h:1091
B_AX_HCI_FC_CH12_FULL_COND_MASK = 0xC00       # GENMASK(11, 10). reg.h:1087
B_AX_PREC_PAGE_CH12_MASK = 0x1FF0000          # GENMASK(24, 16). reg.h:1096
DLE_WAIT_CNT = 2000                           # mac.h:598 (1us poll budget)

# --- M3: efuse access. [SRC] efuse.c:84-300, reg.h:8-15, 63-72, 180-181. ------------------------
R_AX_EFUSE_CTRL = 0x0030                      # reg.h:63
B_AX_EF_RDY = 1 << 29                         # reg.h:65
B_AX_EF_ADDR_MASK = 0x7FF0000                 # GENMASK(26, 16). reg.h:67
R_AX_SYS_WL_EFUSE_CTRL = 0x000A               # reg.h:8
B_AX_AUTOLOAD_SUS = 1 << 5                    # reg.h:9

# --- M3: firmware register mailbox (H2CREG/C2HREG). [SRC] fw.c:9219-9295, fw.h:99-122, reg.h:508-517. ---
R_AX_H2CREG_DATA0_V1 = 0x7140                 # reg.h:508
R_AX_H2CREG_DATA1_V1 = 0x7144                 # reg.h:509
R_AX_H2CREG_DATA2_V1 = 0x7148                 # reg.h:510
R_AX_H2CREG_DATA3_V1 = 0x714C                 # reg.h:511
R_AX_C2HREG_DATA0_V1 = 0x7150                 # reg.h:512
R_AX_C2HREG_DATA1_V1 = 0x7154                 # reg.h:513
R_AX_C2HREG_DATA2_V1 = 0x7158                 # reg.h:514
R_AX_C2HREG_DATA3_V1 = 0x715C                 # reg.h:515
R_AX_H2CREG_CTRL_V1 = 0x7160                  # reg.h:516
R_AX_C2HREG_CTRL_V1 = 0x7164                  # reg.h:517
B_AX_H2CREG_TRIGGER = 1 << 0                  # reg.h:542
B_AX_UDM1_HALMAC_H2C_DEQ_CNT = 0x0F           # GENMASK(11, 8) >> 8. reg.h:247
B_AX_UDM1_HALMAC_C2H_ENQ_CNT = 0xF0           # GENMASK(15, 12) >> 8. reg.h:246
RTW89_H2CREG_HDR_FUNC_MASK = 0x7F             # GENMASK(6, 0). fw.h:101
RTW89_H2CREG_HDR_LEN_MASK = 0xF00             # GENMASK(11, 8). fw.h:102
RTW89_C2HREG_HDR_FUNC_MASK = 0x7F             # GENMASK(6, 0). fw.h:25
RTW89_C2HREG_HDR_LEN_MASK = 0xF00             # GENMASK(11, 8). fw.h:27
RTW89_H2CREG_MAX = 4                          # fw.h:117
RTW89_C2HREG_MAX = 4                          # fw.h:118
RTW89_H2CREG_HDR_LEN = 2                      # fw.h:120
RTW89_C2HREG_HDR_LEN = 2                      # fw.h:119
RTW89_C2H_TIMEOUT_USB = 4000                  # fw.h:122 (kernel budget)
# Python's poll interval is a USB control transfer (~1ms), not the kernel's 1us MMIO read, so
# the kernel's 4ms USB budget can expire before the firmware reply is observed. Use a budget that
# covers the same number of register reads the kernel would get.
C2H_TIMEOUT_USB_POLL_US = 200_000
H2C_REG_IDLE_WAIT_US = 5000                   # fw.c:9228 (read_poll_timeout budget)
RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE = 3       # fw.h:149
RTW89_FWCMD_C2HREG_FUNC_PHY_CAP = 3           # fw.h:93
RTW89_H2CREG_GET_FEATURE_PART_NUM = 0xFF0000  # GENMASK(23, 16). fw.h:115
RTW89_C2HREG_PHYCAP_W0_RX_NSS = 0xFF0000      # GENMASK(23, 16). fw.h:41
RTW89_C2HREG_PHYCAP_W1_TX_NSS = 0x000000FF    # GENMASK(7, 0). fw.h:43
RTW89_C2HREG_PHYCAP_W1_PROT = 0x0000FF00      # GENMASK(15, 8). fw.h:44
RTW89_C2HREG_PHYCAP_W1_PROT_11BE = 4          # fw.h:48
RTW89_C2HREG_PHYCAP_W3_ANT_TX_NUM = 0x0000FF00  # GENMASK(15, 8). fw.h:52
RTW89_C2HREG_PHYCAP_W3_ANT_RX_NUM = 0x00FF0000  # GENMASK(23, 16). fw.h:53

# 8852C chip limits used by setup_phycap. [SRC] rtw8852c.c:3226-3228
RTW89_8852C_RF_PATH_NUM = 2
RTW89_8852C_TX_NSS = 2
RTW89_8852C_RX_NSS = 2
RF_A = 1 << 0                                 # core.h:1101
RF_B = 1 << 1                                 # core.h:1102

# --- M3: mac_init — SCC DLE/HFC profile, sys_init, trx_init, USB mac_post_init. ---
# The kernel indexes its tables by HCI type (rtw89_hci_dle_type) and the 8852C is the chip where
# USB 2.0 and USB 3.0 get *different* DLE rows (_dle_mem_usb2 vs _dle_mem_usb3). HFC does not
# differ: qta_def.hfc_param_ini points at rtw8852c_hfc_param_ini_usb for both USB entries.
# [SRC] rtw8852c.c:40-135, 3173-3181; usb.c:1293-1296; core.h:336-343; mac.c:1913, 1925-1929.

# DLE page-pool sizes (pge_size, lnk_pge_num, unlnk_pge_num).
SCC_USB2_WDE_SIZE = (64, 384, 0)              # wde_size31. mac.c:1756
SCC_USB2_PLE_SIZE = (128, 3374, 18)           # ple_size34. mac.c:1789
SCC_USB3_WDE_SIZE = (64, 354, 30)             # wde_size17. mac.c:1745
SCC_USB3_PLE_SIZE = (128, 3368, 24)           # ple_size17. mac.c:1776
DLFW_WDE_SIZE = (64, 0, 2048)                 # wde_size18 (both USB types). mac.c:1747
DLFW_PLE_SIZE = (128, 2544, 16)               # ple_size18. mac.c:1778

# WDE quota (hif, wcpu, pkt_in, cpu_io). [SRC] core.h:5340 struct rtw89_wde_quota.
SCC_USB2_WDE_QT = (338, 6, 0, 40)             # wde_qt31. mac.c:1820
SCC_USB3_WDE_QT = (344, 2, 0, 8)              # wde_qt16. mac.c:1809
DLFW_WDE_QT = (0, 0, 0, 0)                    # wde_qt17. mac.c:1811

# PLE quota in cma0_tx .. h2d order (the struct field order). [SRC] core.h:5349. cma0_dma is the
# RX quota _rmac_init derives the max MPDU length from (mac.c:1928, 2961-2965).
SCC_USB2_PLE_MIN_QT = (1560, 0, 16, 48, 13, 13, 390, 0, 32, 38, 8, 16, 0)   # ple_qt78. mac.c:1877
SCC_USB2_PLE_MAX_QT = (1560, 0, 32, 48, 1253, 13, 1630, 0, 1272, 38, 120, 1256, 0)  # ple_qt79. mac.c:1879
SCC_USB3_PLE_MIN_QT = (1068, 0, 16, 48, 4, 13, 178, 0, 16, 1, 8, 16, 0)     # ple_qt42. mac.c:1853
SCC_USB3_PLE_MAX_QT = (3068, 0, 32, 48, 4, 13, 178, 0, 16, 1, 8, 16, 0)     # ple_qt43. mac.c:1855
DLFW_PLE_MIN_QT = (0, 0, 16, 256, 0, 0, 0, 0, 0, 0, 0, 0, 0)                # ple_qt44. mac.c:1857
DLFW_PLE_MAX_QT = (0, 0, 32, 256, 0, 0, 0, 0, 0, 0, 0, 0, 0)                # ple_qt45. mac.c:1860

# HFC channel config for the SCC profile: (min, max, grp) per ACH0..B1HI + FWCMDQ.
SCC_HFC_CH_CFG = (
    (18, 344, 0), (0, 0, 0), (18, 344, 0), (0, 0, 0),
    (18, 344, 0), (0, 0, 0), (18, 344, 0), (0, 0, 0),
    (18, 344, 0), (0, 0, 0), (18, 344, 0), (0, 0, 0),
    (0, 0, 0),
)
SCC_HFC_PUB = (344, 0, 344, 0)                # grp0, grp1, pub_max, wp_thrd
SCC_HFC_PREC = (9, 32, 146, 146, 1, 1, 1, 1)  # ch011, h2c, wp07, wp811, + 4 full conds
HFC_MODE_STF = 1                              # RTW89_HCIFC_STF. core.h:6068

R_AX_ACH0_PAGE_CTRL_V1 = 0x1710               # reg.h:461
R_AX_ACH0_PAGE_INFO_V1 = 0x1750               # reg.h:474
R_AX_PUB_PAGE_CTRL1_V1 = 0x1790               # reg.h:489
R_AX_PUB_PAGE_CTRL2_V1 = 0x1794               # reg.h:490
R_AX_WP_PAGE_CTRL1_V1 = 0x17A0                # reg.h:493
R_AX_WP_PAGE_CTRL2_V1 = 0x17A4                # reg.h:494
B_AX_MIN_PG_MASK = 0x1FFF                     # GENMASK(12, 0). reg.h:1100
B_AX_MAX_PG_MASK = 0x1FFF0000                 # GENMASK(28, 16). reg.h:1099
B_AX_GRP = 1 << 31                            # reg.h:1101
B_AX_PUBPG_G0_MASK = 0x1FFF                   # GENMASK(12, 0). reg.h:1137
B_AX_PUBPG_G1_MASK = 0x1FFF0000               # GENMASK(28, 16). reg.h:1136
B_AX_PUBPG_ALL_MASK = 0x1FFF                  # GENMASK(12, 0). reg.h:1141
B_AX_WP_THRD_MASK = 0x1FFF                    # GENMASK(12, 0). reg.h:1154
B_AX_PREC_PAGE_CH011_MASK = 0x1FF             # GENMASK(8, 0). reg.h:1110
B_AX_PREC_PAGE_WP_CH07_MASK = 0x1FF           # GENMASK(8, 0). reg.h:1152
B_AX_PREC_PAGE_WP_CH811_MASK = 0x1FF0000      # GENMASK(24, 16). reg.h:1151
B_AX_HCI_FC_MODE_MASK = 0x6                   # GENMASK(2, 1). reg.h:1089
B_AX_HCI_FC_WD_FULL_COND_MASK = 0x30          # GENMASK(5, 4). reg.h:1086
B_AX_HCI_FC_WP_CH07_FULL_COND_MASK = 0xC0     # GENMASK(7, 6). reg.h:1085
B_AX_HCI_FC_WP_CH811_FULL_COND_MASK = 0x300   # GENMASK(9, 8). reg.h:1084
B_AX_AVAL_PG_MASK = 0x0FFF0000                # GENMASK(27, 16). reg.h:1115
B_AX_USE_PG_MASK = 0x1FFF                     # GENMASK(12, 0). reg.h:1116
R_AX_PUB_PAGE_INFO1_V1 = 0x1798               # reg.h:491
R_AX_PUB_PAGE_INFO2_V1 = 0x179C               # reg.h:492
R_AX_PUB_PAGE_INFO3_V1 = 0x178C               # reg.h:488
R_AX_WP_PAGE_INFO1_V1 = 0x17A8                # reg.h:495
B_AX_G0_USE_PG_MASK = 0x1FFF                  # GENMASK(12, 0). reg.h:1129
B_AX_G1_USE_PG_MASK = 0x1FFF0000              # GENMASK(28, 16). reg.h:1128
B_AX_G0_AVAL_PG_MASK = 0x1FFF                 # GENMASK(12, 0). reg.h:1124
B_AX_G1_AVAL_PG_MASK = 0x1FFF0000             # GENMASK(28, 16). reg.h:1123
B_AX_PUB_AVAL_PG_MASK = 0x1FFF                # GENMASK(12, 0). reg.h:1133
B_AX_WP_AVAL_PG_MASK = 0x1FFF0000             # GENMASK(28, 16). reg.h:1157

# rtw89_mac_gen_ax function-enable bits (dmac_func_en_ax / cmac_func_en_ax). [SRC] mac.c:1656-1710
B_AX_DMAC_CRPRT = 1 << 31
B_AX_DMAC_FUNC_EN_MASK = B_AX_MAC_FUNC_EN | B_AX_DMAC_FUNC_EN
B_AX_MAC_SEC_CLK_EN = 1 << 16
B_AX_DLE_CPUIO_CLK_EN = 1 << 19
B_AX_PKT_IN_CLK_EN = 1 << 20
B_AX_STA_SCH_CLK_EN = 1 << 24
B_AX_TXPKT_CTRL_CLK_EN = 1 << 25
B_AX_WD_RLS_CLK_EN = 1 << 27
B_AX_BBRPT_CLK_EN = 1 << 17
B_AX_CMAC_CRPRT = 1 << 31
B_AX_CMAC_CKEN = 1 << 30
B_AX_PHYINTF_CKEN = 1 << 5
B_AX_CMAC_DMA_CKEN = 1 << 4
B_AX_PTCLTOP_CKEN = 1 << 3
B_AX_SCHEDULER_CKEN = 1 << 2
B_AX_TMAC_CKEN = 1 << 1
B_AX_RMAC_CKEN = 1 << 0

# trx_init sub-inits. [SRC] mac.c:2425-3080
R_AX_SS_CTRL = 0x9E10
B_AX_SS_EN = 1 << 0
B_AX_SS_INIT_DONE_1 = 1 << 31
B_AX_SS_WARM_INIT_FLG = 1 << 29
B_AX_SS_NONEMPTY_SS2FINFO_EN = 1 << 28
TRXCFG_WAIT_CNT = 2000
R_AX_ACTION_FWD0 = 0x9C04
TRXCFG_MPDU_PROC_ACT_FRWD = 0x02A95A95
R_AX_TF_FWD = 0x9C14
TRXCFG_MPDU_PROC_TF_FRWD = 0x0000AA55
R_AX_MPDU_PROC = 0x9C00
B_AX_APPEND_FCS = 1 << 0
B_AX_A_ICV_ERR = 1 << 1
R_AX_CUT_AMSDU_CTRL = 0x9C40
TRXCFG_MPDU_PROC_CUT_CTRL = 0x010E05F0
R_AX_SEC_ENG_CTRL = 0x9D00
B_AX_CLK_EN_CGCMP = 1 << 10
B_AX_CLK_EN_WAPI = 1 << 9
B_AX_CLK_EN_WEP_TKIP = 1 << 8
B_AX_SEC_TX_ENC = 1 << 0
B_AX_SEC_RX_DEC = 1 << 1
B_AX_MC_DEC = 1 << 3
B_AX_BC_DEC = 1 << 2
B_AX_UC_MGNT_DEC = 1 << 4
B_AX_TX_PARTIAL_MODE = 1 << 11
R_AX_SEC_MPDU_PROC = 0x9D04
B_AX_APPEND_ICV = 1 << 1
B_AX_APPEND_MIC = 1 << 0
R_AX_SEC_DEBUG1 = 0x9D1C
B_AX_TX_TIMEOUT_SEL_MASK = 0xC0000000
AX_TX_TO_VAL = 0x2
R_AX_ADDR_CAM_CTRL = 0xCE34
B_AX_ADDR_CAM_RANGE_MASK = 0xFF0000
B_AX_ADDR_CAM_CLR = 1 << 8
B_AX_ADDR_CAM_EN = 1 << 0
R_AX_PREBKF_CFG_1 = 0xC33C
B_AX_SIFS_MACTXEN_T1_MASK = 0x7F
SIFS_MACTXEN_T1_V1 = 0x41
R_AX_CCA_CFG_0 = 0xC340
B_AX_BTCCA_EN = 1 << 5
R_AX_PREBKF_CFG_0 = 0xC338
B_AX_PREBKF_TIME_MASK = 0x1F
SCH_PREBKF_24US = 0x18
R_AX_MGNT_FLTR = 0xCE28
R_AX_CTRL_FLTR = 0xCE24
R_AX_DATA_FLTR = 0xCE2C
RX_FLTR_FRAME_TO_HOST = 0x55555555
R_AX_RX_FLTR_OPT = 0xCE20
R_AX_PLCP_HDR_FLTR = 0xCE04
B_AX_CCK_CRC_CHK = 1 << 0
B_AX_CCK_SIG_CHK = 1 << 1
B_AX_LSIG_PARITY_CHK_EN = 1 << 2
B_AX_SIGA_CRC_CHK = 1 << 3
B_AX_VHT_SU_SIGB_CRC_CHK = 1 << 4
B_AX_VHT_MU_SIGB_CRC_CHK = 1 << 5
B_AX_HE_SIGB_CRC_CHK = 1 << 6
DEFAULT_AX_RX_FLTR = 0x030044BE
B_AX_SNIFFER_MODE = 1 << 0
B_AX_A_PWR_MGNT = 1 << 10
B_AX_STOP_RX_IN = 1 << 11
B_AX_A_CRC32_ERR = 1 << 11
B_AX_A_FTM_REQ = 1 << 14
B_AX_RX_FLTR_CFG_MASK = 0xFFC0FFFF          # ~B_AX_RX_MPDU_MAX_LEN_MASK (preserves max len bits 21:16)
SNIFFER_AX_RX_FLTR = DEFAULT_AX_RX_FLTR | B_AX_SNIFFER_MODE | B_AX_A_CRC32_ERR
R_AX_PPDU_STAT = 0xCE40
R_AX_HW_RPT_FWD = 0x9C18

B_AX_BCN_DROP_ALLOW = 1 << 14                 # reg.h:2388

R_AX_P0MB_HGQ_WINDOW_CFG_0 = 0xC590
R_AX_MD_TSFT_STMP_CTL = 0xCA08
R_AX_MBSSID_CTRL = 0xC568
R_AX_MBSSID_DROP_0 = 0xC63C
R_AX_PTCL_BSS_COLOR_0 = 0xC6A0
R_AX_CCA_CONTROL = 0xC390
B_AX_TB_CHK_BASIC_NAV = 1 << 30
B_AX_TB_CHK_BTCCA = 1 << 29
B_AX_TB_CHK_EDCCA = 1 << 28
B_AX_TB_CHK_CCA_P20 = 1 << 24
B_AX_SIFS_CHK_BTCCA = 1 << 21
B_AX_SIFS_CHK_CCA_P20 = 1 << 16
B_AX_CTN_CHK_INTRA_NAV = 1 << 7
B_AX_CTN_CHK_BASIC_NAV = 1 << 6
B_AX_CTN_CHK_BTCCA = 1 << 5
B_AX_CTN_CHK_EDCCA = 1 << 4
B_AX_CTN_CHK_CCA_S80 = 1 << 3
B_AX_CTN_CHK_CCA_S40 = 1 << 2
B_AX_CTN_CHK_CCA_S20 = 1 << 1
B_AX_CTN_CHK_CCA_P20 = 1 << 0
B_AX_TB_CHK_TX_NAV = 1 << 31
B_AX_TB_CHK_CCA_S80 = 1 << 27
B_AX_TB_CHK_CCA_S40 = 1 << 26
B_AX_TB_CHK_CCA_S20 = 1 << 25
B_AX_SIFS_CHK_CCA_S80 = 1 << 19
B_AX_SIFS_CHK_CCA_S40 = 1 << 18
B_AX_SIFS_CHK_CCA_S20 = 1 << 17
B_AX_CTN_CHK_TXNAV = 1 << 8
B_AX_SIFS_CHK_EDCCA = 1 << 20
R_AX_RSP_CHK_SIG = 0xCC00
B_AX_RSP_CHK_TXNAV = 1 << 19
B_AX_RSP_CHK_INTRA_NAV = 1 << 20
B_AX_RSP_CHK_BASIC_NAV = 1 << 21
R_AX_TRXPTCL_RESP_0 = 0xCC04
B_AX_RSP_CHK_SEC_CCA_80 = 1 << 28
B_AX_RSP_CHK_SEC_CCA_40 = 1 << 27
B_AX_RSP_CHK_SEC_CCA_20 = 1 << 26
B_AX_RSP_CHK_BTCCA = 1 << 25
B_AX_RSP_CHK_EDCCA = 1 << 24
B_AX_RSP_CHK_CCA = 1 << 23
R_AX_WMAC_NAV_CTL = 0xCC80
B_AX_WMAC_PLCP_UP_NAV_EN = 1 << 17
B_AX_WMAC_TF_UP_NAV_EN = 1 << 16
B_AX_WMAC_NAV_UPPER_EN = 1 << 26
B_AX_WMAC_NAV_UPPER_MASK = 0xFF00
NAV_25MS = 0xC4
R_AX_RX_SR_CTRL = 0xCE4A
B_AX_SR_EN = 1 << 0
R_AX_BSSID_SRC_CTRL = 0xCE4B
B_AX_PLCP_SRC_EN = 1 << 0
R_AX_MAC_LOOPBACK = 0xCC20
B_AX_MACLBK_EN = 1 << 0
R_AX_TCR0 = 0xCA00
B_AX_TCR_UDF_THSD_MASK = 0x7F0000
TCR_UDF_THSD = 0x6
R_AX_TXD_FIFO_CTRL = 0xCA1C
B_AX_TXDFIFO_HIGH_MCS_THRE_MASK = 0xF000
TXDFIFO_HIGH_MCS_THRE = 0x7
B_AX_TXDFIFO_LOW_MCS_THRE_MASK = 0xF00
TXDFIFO_LOW_MCS_THRE = 0x7
B_AX_WMAC_SPEC_SIFS_CCK_MASK = 0xFF
WMAC_SPEC_SIFS_CCK = 0xA
B_AX_WMAC_SPEC_SIFS_OFDM_MASK = 0xFF00
WMAC_SPEC_SIFS_OFDM_52C = 0x11
R_AX_RXTRIG_TEST_USER_2 = 0xCCB0
B_AX_RXTRIG_FCSCHK_EN = 1 << 20
R_AX_TRXPTCL_RRSR_CTL_0 = 0xCC08
B_AX_WMAC_RESP_REF_RATE_SEL = 1 << 9
R_AX_PTCL_RRSR1 = 0xC090
B_AX_RSC_MASK = 0xC0
R_AX_RESPBA_CAM_CTRL = 0xCE3C
B_AX_BACAM_RST_MASK = 0x3
S_AX_BACAM_RST_ALL = 0x2
B_AX_SSN_SEL = 1 << 2
R_AX_DLK_PROTECT_CTL = 0xCE02
B_AX_RX_DLK_DATA_TIME_MASK = 0xF0
B_AX_RX_DLK_CCA_TIME_MASK = 0xFF00
R_AX_RCR = 0xCE00
B_AX_CH_EN_MASK = 0xF
B_AX_RX_MPDU_MAX_LEN_MASK = 0x3F0000
R_AX_TX_SUB_CARRIER_VALUE = 0xC088
B_AX_TXSC_20M_MASK = 0xF
B_AX_TXSC_40M_MASK = 0xF0
B_AX_TXSC_80M_MASK = 0xF00
R_AX_SIFS_SETTING = 0xC624
B_AX_HW_CTS2SELF_PKT_LEN_TH_MASK = 0xFF000000
S_AX_CTS2S_TH_1K = 4
B_AX_HW_CTS2SELF_PKT_LEN_TH_TWW_MASK = 0xFC0000
S_AX_CTS2S_TH_SEC_256B = 1
B_AX_HW_CTS2SELF_EN = 1 << 16
R_AX_PTCL_FSM_MON = 0xC6E8
B_AX_PTCL_TX_ARB_TO_THR_MASK = 0x3F
S_AX_PTCL_TO_2MS = 0x3F
B_AX_PTCL_TX_ARB_TO_MODE = 1 << 6
R_AX_PTCL_COMMON_SETTING_0 = 0xC600
B_AX_CMAC_TX_MODE_0 = 1 << 0
B_AX_CMAC_TX_MODE_1 = 1 << 1
B_AX_PTCL_TRIGGER_SS_EN_0 = 1 << 2
B_AX_PTCL_TRIGGER_SS_EN_1 = 1 << 3
B_AX_PTCL_TRIGGER_SS_EN_UL = 1 << 4
R_AX_PTCLRPT_FULL_HDL = 0xC660
B_AX_SPE_RPT_PATH_MASK = 0x30
FWD_TO_WLCPU = 1
R_AX_SCH_EXT_CTRL = 0xC3FC
B_AX_PORT_RST_TSF_ADV = 1 << 1
R_AX_RSP_CHK_SIG_L = 0xCC00

# IMR enable masks. [SRC] mac.c:3744-3943, rtw8852c.c:rtw8852c_imr_info
R_AX_WDRLS_ERR_IMR = 0x9430
B_AX_WDRLS_IMR_EN_CLR = 0x3337
B_AX_WDRLS_IMR_SET_V1 = 0x3337
R_AX_SEC_ERROR_FLAG_IMR = 0x9D2C
B_AX_TX_HANG_IMR = 1 << 0
B_AX_RX_HANG_IMR = 1 << 1
R_AX_MPDU_TX_ERR_IMR = 0x9BF4
B_AX_TX_GET_ERRPKTID_INT_EN = 1 << 1
B_AX_TX_NXT_ERRPKTID_INT_EN = 1 << 2
B_AX_TX_MPDU_SIZE_ZERO_INT_EN = 1 << 3
B_AX_TX_OFFSET_ERR_INT_EN = 1 << 4
B_AX_TX_HDR3_SIZE_ERR_INT_EN = 1 << 5
B_AX_TX_ETH_TYPE_ERR_EN = 1 << 6
B_AX_TX_LLC_PRE_ERR_EN = 1 << 7
B_AX_TX_NW_TYPE_ERR_EN = 1 << 8
B_AX_TX_KSRCH_ERR_EN = 1 << 9
B_AX_MPDU_TX_IMR_SET_V1 = 0x36E
R_AX_MPDU_RX_ERR_IMR = 0x9CF4
B_AX_GETPKTID_ERR_INT_EN = 1 << 0
B_AX_MHDRLEN_ERR_INT_EN = 1 << 1
B_AX_RPT_ERR_INT_EN = 1 << 3
B_AX_MPDU_RX_IMR_SET_V1 = 0x8
R_AX_STA_SCHEDULER_ERR_IMR = 0x9EF0
B_AX_SEARCH_HANG_TIMEOUT_INT_EN = 1 << 0
B_AX_RPT_HANG_TIMEOUT_INT_EN = 1 << 1
B_AX_PLE_B_PKTID_ERR_INT_EN = 1 << 2
B_AX_STA_SCHEDULER_IMR_SET = 0x7
R_AX_TXPKTCTL_B0_ERRFLAG_IMR = 0x9F78
R_AX_TXPKTCTL_B1_ERRFLAG_IMR = 0x9FB8
B_AX_TXPKTCTL_IMR_B0_CLR_V1 = 0x350F0F
B_AX_TXPKTCTL_IMR_B0_SET_V1 = 0x350B03
B_AX_TXPKTCTL_IMR_B1_CLR_V1 = 0x350F0F
B_AX_TXPKTCTL_IMR_B1_SET_V1 = 0x350F03
R_AX_WDE_ERR_IMR = 0x8C38
B_AX_WDE_IMR_CLR_V1 = 0x3F0FF3FF
B_AX_WDE_IMR_SET_V1 = 0x3F0FF3FF
R_AX_PLE_ERR_IMR = 0x9038
B_AX_PLE_IMR_CLR_V1 = 0x3F0FF3FF
B_AX_PLE_IMR_SET_V1 = 0x3F0FF3FF
R_AX_PKTIN_ERR_IMR = 0x9A20
B_AX_PKTIN_GETPKTID_ERR_INT_EN = 1 << 0
R_AX_HOST_DISPATCHER_ERR_IMR = 0x8850
B_AX_HOST_DISP_IMR_CLR_V1 = 0xFFD7FFFF
B_AX_HOST_DISP_IMR_SET_V1 = 0x0C100060
R_AX_CPU_DISPATCHER_ERR_IMR = 0x8854
B_AX_CPU_DISP_IMR_CLR_V1 = 0x7F7BFFFD
B_AX_CPU_DISP_IMR_SET_V1 = 0x36000060
R_AX_OTHER_DISPATCHER_ERR_IMR = 0x8858
B_AX_OTHER_DISP_IMR_CLR_V1 = 0xFFFFDFDF
B_AX_OTHER_DISP_IMR_SET_V1 = 0x303CC000
R_AX_CPUIO_ERR_IMR = 0x9840
B_AX_CPUIO_IMR_CLR = 0x1111
B_AX_CPUIO_IMR_SET = 0x1111
R_AX_BBRPT_COM_ERR_IMR = 0x9608
B_AX_BBRPT_COM_NULL_PLPKTID_ERR_INT_EN = 1 << 0
R_AX_BBRPT_CHINFO_ERR_IMR = 0x9628
B_AX_BBRPT_CHINFO_IMR_CLR = 0xFF
R_AX_BBRPT_CHINFO_IMR_SET_V1 = 0xFF
R_AX_BBRPT_DFS_ERR_IMR = 0x9638
B_AX_BBRPT_DFS_TO_ERR_INT_EN = 1 << 0
R_AX_LA_ERRFLAG = 0x966C
B_AX_LA_IMR_DATA_LOSS_ERR = 1 << 0
R_AX_SCHEDULE_ERR_IMR = 0xC3E8
B_AX_SORT_NON_IDLE_ERR_INT_EN = 1 << 1
B_AX_FSM_TIMEOUT_ERR_INT_EN = 1 << 0
R_AX_PTCL_IMR0 = 0xC6C0
B_AX_PTCL_IMR_CLR_V1 = 0x3
B_AX_PTCL_IMR_SET_V1 = 0x3
R_AX_RX_ERR_FLAG_IMR = 0xC804
B_AX_RX_ERR_IMR_CLR_V1 = 0x7FFFFF06
R_AX_TX_ERR_FLAG_IMR = 0xC870
B_AX_TX_ERR_IMR_CLR_V1 = 0xFF00C000
B_AX_TX_ERR_IMR_SET_V1 = 0xFF00C000
R_AX_PHYINFO_ERR_IMR_V1 = 0xCCF8
B_AX_PHYINFO_IMR_CLR_V1 = 0x3F
B_AX_PHYINFO_IMR_SET_V1 = 0x3F
R_AX_RX_ERR_IMR = 0xCEF8
B_AX_RMAC_IMR_CLR_V1 = 0x3FF
B_AX_RMAC_IMR_SET_V1 = 0x3FF
R_AX_TRXPTCL_ERROR_INDICA_MASK = 0xCCBC
B_AX_TMAC_IMR_CLR_V1 = 0x1FF
B_AX_TMAC_IMR_SET_V1 = 0x17F
DMAC_ERR_IMR_EN = 0xFFFFFFFF
DMAC_ERR_IMR_DIS = 0
CMAC0_ERR_IMR_EN = 0xFFFFFFFF
CMAC0_ERR_IMR_DIS = 0

# chip_func_en_ax is a no-op on the 8852C (only 8852A/885xB touch SPS_DIG_ON_CTRL0).
# enable_bb_rf / disable_bb_rf. [SRC] rtw8852c.c:3030-3074
R_AX_AFE_OFF_CTRL1 = 0x0444
B_AX_S0_LDO_VSEL_F_MASK = 0x600000
B_AX_S1_LDO_VSEL_F_MASK = 0x03000000
XTAL0 = 0x0
XTAL3 = 0x3
FULL_BIT_MASK = 0xFF

# mac_post_init (USB): RX aggregation + endpoint/bulk-size config. [SRC] usb.c:886-925
R_BE_RXAGG_0_V1 = 0x10C40
R_BE_RXAGG_1_V1 = 0x10C44
R_AX_RXAGG_0_V1 = 0x6000
R_AX_RXAGG_1_V1 = 0x6004

# --- M3: remaining IMR + host RPR + USB post-init constants
B_AX_RX_ERR_IMR_SET_V1 = 0x7FFFFF06
B_AX_BBRPT_CHINFO_IMR_SET_V1 = 0xFF
R_AX_DMAC_ERR_IMR = 0x8520
R_AX_CMAC_ERR_IMR = 0xC160
R_AX_WDRLS_CFG = 0x9408
B_AX_WDRLS_MODE_MASK = 0x3
RPR_MODE_STF = 1
R_AX_RLSRPT0_CFG0 = 0x9410
B_AX_RLSRPT0_FLTR_MAP_MASK = 0x0F000000
R_AX_RLSRPT0_CFG1 = 0x9414
B_AX_RLSRPT0_TO_MASK = 0x00FF0000
B_AX_RLSRPT0_AGGNUM_MASK = 0xFF
B_AX_RSP_STATIC_RTS_CHK_SERV_BW_EN = 1 << 30
B_AX_RXAGG_0_EN = 1 << 31
B_AX_RXAGG_0_NUM_TH = 0x00FF0000
B_AX_RXAGG_0_TIME_32US_TH = 0x0000FF00
B_AX_RXAGG_0_BUF_SZ_1K = 0x000000FF
R_AX_USB_ENDPOINT_2_NUMP_V1 = 0x5069

# Indirect SRAM access and DMAC/CMAC tables. [SRC] mac.c:4413-4440, mac.h:302-353, reg.h:357
R_AX_FILTER_MODEL_ADDR = 0x0C04
R_AX_INDIR_ACCESS_ENTRY = 0x40000
DMAC_TBL_BASE_ADDR = 0x18800000
CMAC_TBL_BASE_ADDR = 0x18840000
CCTL_INFO_SIZE = 32

# Secondary EDCCA & Packet Detector controls. [SRC] reg.h:9017-9045, rtw8852c.c:1278-1700
R_PD_CTRL = 0x0C3C
B_PD_HIT_DIS = 1 << 9
R_SNDCCA_A1 = 0x0C9C
B_SNDCCA_A1_EN = 0xFF << 12                    # GENMASK(19, 12)
R_SNDCCA_A2 = 0x0CA0
B_SNDCCA_A2_VAL = 0xFF << 12                   # GENMASK(19, 12)


# TX power unit. [SRC] reg.h:3493-3611, rtw8852c.c:2030-2340
R_AX_PWR_RATE_CTRL = 0xD200
R_AX_PWR_RATE_OFST_CTRL = 0xD208
B_AX_PWR_RATE_CTRL_TSSI_MASK = 0x0FFC0000      # GENMASK(27, 10)
R_AX_PWR_COEXT_CTRL = 0xD220
R_AX_PWR_UL_CTRL0 = 0xD240
R_AX_PWR_UL_CTRL2 = 0xD248
R_AX_PWR_UL_TB_1T = 0xD28C
R_AX_PWR_UL_TB_2T = 0xD290
B_AX_PWR_UL_TB_V1_MASK = 0xFF                  # GENMASK(7, 0)
R_AX_PWR_BY_RATE = 0xD2C0                      # 11 dwords through 0xD2E8
R_AX_PWR_LMT = 0xD2EC                          # 20 dwords through 0xD338
R_AX_PWR_RU_LMT = 0xD33C                       # 12 dwords through 0xD368
R_AX_TSSI_CTRL_HEAD = 0xD908
R_AX_TSSI_CTRL_TAIL = 0xD95C
R_AX_BANDEDGE_CFG = 0xD94C
B_AX_BANDEDGE_CFG_IDX_MASK = 0xC0000000        # GENMASK(31, 30)
RR_TM2 = 0x43                                  # reg.h:8640
RR_TM2_OFF = 0x000F0000                        # GENMASK(19, 16)
RR_BIASA = 0x60                                # reg.h:8671
RR_BIASA_TXG = 0x0000F000                      # GENMASK(15, 12)
RR_BIASA_TXA = 0x000F0000                      # GENMASK(19, 16)
