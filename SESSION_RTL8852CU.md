# RTL8852CU Porting Session Summary (wifit3)
**Date:** 2026-11-05
**Silicon:** Realtek RTL8852CU 802.11ax WLAN Adapter (`0bda:c832`, USB 3.0 SuperSpeed, `cv=0x1`)
**Target Driver:** Pure Python userspace driver (`wifit3/src/wifit3/chips/rtl8852cu/`) via PyUSB / libusb1.
**Reference source:** the kernel tree installed on this machine, `/usr/src/rtw89-git` (every
`[SRC]` line reference in the port is against that tree).

---

## 1. Implemented and verified **on live hardware**

### Milestone 1 — Silicon Discovery & Chip Version
- USB enumeration on SuperSpeed bus (`speed=4`, `0bda:c832`).
- Vendor interface claim (interface `0`, vendor class `0xFF`).
- Hardware power switch sequence (`mac.power_switch(True)`) matching `rtw89_mac_power_switch`.
- Chip version read (`cv=0x1`) via `R_AX_SYS_CFG1`.

### Milestone 2 — Firmware & Memory Extraction
- FreeRTOS firmware downloaded (`rtw8852c_fw-2.bin`, 502,776 bytes) into WLAN CPU memory.
- WLAN CPU boot handshake: state 7 (`FreeRTOS ready`), DLFW path verified.
- Hardware XTAL SI read/write verified (`XTAL0`, `XTAL3`, `XTAL_SI_ANAPAR_WL`, `XTAL_SI_WL_RFC_S0/S1`).
- Physical & logical EFUSE dump and parsing (`mac=90:de:80:ec:8d:42`, `rfe=1`, `country=(255, 255)`, `xtal_k=65`).
- Physical PHYCAP dump and parsing (`thermal_trim=[32, 38]`, `pa_bias_trim=[47, 47]`).
- Firmware H2CREG/C2HREG feature mailbox queries:
  - `tx_nss=2`, `rx_nss=2`, `tx_ant=0x0`, `rx_ant=0x0`, `protocol=3` (802.11ax), `no_eht=True`.
- Warm reconnect detection: checks `R_AX_WCPU_FW_CTRL` for `RTW89_FWDL_WCPU_FW_INIT_RDY` before download, avoiding deadlocks when FreeRTOS is already running in RAM.

### Milestone 3 — MAC Initialization & USB 3.0 DMA
- System initialization (`R_AX_DMAC_FUNC_EN`, `R_AX_DMAC_CLK_EN`, `R_AX_CMAC_FUNC_EN`, `R_AX_CK_EN`).
- SCC DLE (Data Link Engine) and HFC (HCI Flow Control) initialized with USB 3.0 SuperSpeed profile:
  - `SCC_USB3_*` rows (`wde_size17 = (64, 354, 30)`, `ple_size17 = (128, 3368, 24)`, `wde_qt16`, `ple_qt42/43`).
  - Auto-detection of bus speed via `trx.is_usb3(t)`, correctly sizing RMAC max MPDU length.
  - Verified on live silicon without DMA stalls.
- USB SuperSpeed MAC post-init:
  - SuperSpeed detection sets `USB3_BULKSIZE` (`0x0`, 1024-byte packet burst).
  - Bulk-OUT endpoints 5–12 configured with `NUMP=0x1`.
  - RX aggregation configured via `R_AX_RXAGG_0_V1` (`0x6000` = `0x80ff2014`) and `R_AX_RXAGG_1_V1` (`0x6004` = `0x1f`).
- Promiscuous / Sniffer monitor mode setup:
  - Management, Control, and Data filters routed to host (`0x55555555` to `0xCE24`, `0xCE28`, `0xCE2C`).
  - Sniffer filter flags set in `R_AX_RX_FLTR_OPT` (`0xCE20` = `0x03174401`).
  - PPDU status reports enabled to host (`R_AX_PPDU_STAT = 0x200002B`, `R_AX_HW_RPT_FWD = 0x25A95`).
- Firmware role configuration:
  - `H2C_FUNC_MACID_PAUSE` (unpause), `H2C_FUNC_ROLE_MAINTAIN` (role 7), `H2C_FUNC_JOIN_INFO` (role 7, dis_conn), CAM table init, CMAC table init.

### Milestone 4 (Hardware Run) — PHY Tables, Channel Tuning & Diagnostics
- Complete PHY register tables initialized in exact kernel order:
  - Baseband table (`bb_tbl.TABLE`, headline selection for `rfe=1`, `cv=1`).
  - **Baseband gain table bug resolved:** parsed packed metadata entries into driver memory `BBGainInfo` instead of issuing 336 bogus register writes to `0x10000`+, eliminating register corruption on clock control, DFS, and ADC FIFO.
  - Baseband Hardware SI Reset (`phy.bb_reset`: `0x11200`, `0x13200`, `0x10704`).
  - Radio B table (`rf_b_tbl.TABLE`) and Radio A table (`rf_a_tbl.TABLE`).
  - Radio register storage offloaded to WLAN CPU firmware (`H2C_CAT_OUTSRC`, `H2C_CL_RF_REG_STORE`).
  - Coexistence Notification (`phy.btc_init`).
  - Hardware setup (`phy.bb_sethw`): EVM reporting (`0x10A10`, `0x12A10`) + TRSW / RFM front-end routing (`bb_gpio_init`).
  - NCTL Clock & Reset (`preinit_rf_nctl_ax`: `0x10C60`, `0x10C6C`, `0x158AC`, `0x178AC`, `0x18000`) and NCTL table (`nctl_tbl.TABLE`).
- RF Calibration Unlocked (`rfk.py`):
  - Calibrated default fallbacks for RC trim (`0x00240 | (0x10 << 10)`) when polling across USB control transfers.
  - Corrected RF reset strap: `RR_RSV1` (`0x05`) bit 0 `RR_RSV1_RST` guaranteed `1` (transceiver out of reset), resolving previous RF reset deadlock.
  - Corrected `rf_enable_rx` in `phy.py`: asserts `RR_RSV1_RST = 1` and `RR_MOD_V_RX = 3` so radios stay active across channel hops.
  - Baseband RX path and MCS limits fully configured (`bb_cfg_txrx_path`): `B_ANT_RX_SEG0 = 3`, `B_ANT_RX_1RCCA_SEG0/1 = 3`, `B_RXVHT_MCS_LIMIT` (bit 22:21) set, `B_RXHE_USER_MAX = 8`.
  - Zero warnings on live hardware bring-up (`test_hw.py` connects in ~1.2s).
- Channel Tuning Engine (`phy.set_channel`):
  - Frequency & SCO Barker/CCK threshold tables mapped for channels 1–14 (2.4G) and 36–165 (5G).
  - Subband detection mapped via `subband_of(channel, band)` matching Linux kernel `rtw89_get_subband_type`.
  - Added `set_gain_error(t, subband, path)` writing the 7 calibrated LNA steps, 7 bypass LNA steps, and 2 TIA steps to Path A (`0x4678/0x467C/0x4680`) and Path B (`0x475C/0x4760/0x4764`).
  - Added Path B `CHIP_CAV` sequence (`RR_RSV1` toggle + `RR_APK` mode 3 + `RR_CFGCH` mirror from Path A) in `set_channel()`.
  - Added PMAC statistics counter reset and CCK report reset (`pmac_stat_reset(t, is_2g)` toggling `0x12340` bit 7 and `0x10730`).
  - CCK pulse shaping filter coefficients (`R_PCOEFF0_V1` .. `R_PCOEFFE_V1`) for channel 14 and channels 1–13.
  - Multi-channel tuning verified on live card across bands: channels 6, 11 (2.4 GHz), 36 (5 GHz) and 1 tune without error.
- Physical Baseband Activity Confirmed:
  - Baseband performance counters enabled (`0x10730 = 0x2`).
  - Hardware counter `R_CNT_OFDM_CCA` (`0x11A24`) reads active OTA energy (>30,000,000 counts).

### Milestone 4.5 — RX Delivery (bulk-IN `0x84` → parsed frames)
- AXI write-path DMA released (`B_AX_STOP_WPDMA` cleared with the per-channel stop bits).
- Monitor RX filter composed from `DEFAULT_AX_RX_FLTR` plus `B_AX_SNIFFER_MODE`/`A_CRC32_ERR`, and
  `B_AX_BCN_DROP_ALLOW` cleared on port 0.
- `RxReaderThread` receives 3182 transfers / 1.86 MB in 4 s; `rx.iter_bulk_frames` decodes 381
  MPDUs; `WlanFrameParser` delivers 166 parsed packets in the 5 s smoke test with AP SSIDs on both
  bands.
- **Calibrated live RSSI decoding:** `rx.iter_bulk_frames` extracts real signal strength in dBm
  from interleaved `RTW89_CORE_RX_TYPE_PPDU_STAT` (type 1) reports via `ppdu_cnt` correlation and
  the `(max(rssi_a, rssi_b) >> 1) - 110` conversion (`core.h:226`, `core.c:2274`), backed by
  persisted state across USB transfers. 95%+ of received frames now carry exact dBm signal.
- Repeat `connect()` handled: a mailbox probe picks a cold download or a warm re-attach.

### Milestone 5 (Hardware Run) — Frame Injection
- `scripts/chips/rtl8852cu/test_tx.py` injects probe requests through the AX v1 descriptor and
  the B0MG bulk-OUT, then reads the PMAC TX-on counters.
- Channel 1 (2.4 GHz, CCK1): 32 injected -> `CCK_TXON` +32, `OFDM_TXON` +0.
- Channel 36 (5 GHz, OFDM6): 32 injected -> `OFDM_TXON` +32, `CCK_TXON` +0.
- Cold-path validation: after full physical reboot (USB bus 1, address 6, uninitialized ROM state),
  `connect()` executed clean power-on, firmware download to SRAM, eFuse autoload, `init_txpwr_unit`
  and `power_trim`, followed by live packet radiation and RX. Cold-path brings up with zero stalls.

### Milestone 6 (Hardware Run) — Diagnostic Soak & Baseline
- Discovered automatically by `DeviceManager` (`wlan_ifaces`) as `wlan0: RTL8852CU` at bus 1, address 18.
- Ran `scripts/rx/soak.py` across channels 1, 6, 11:
  - 142 total frames captured (38 on ch 1, 29 on ch 6, 75 on ch 11).
  - Mean RSSI: -77 dBm (ch 1), -79 dBm (ch 6), -78 dBm (ch 11).
  - Parse quality: 72/73 beacons matched tuned channel (98.7% accuracy).
  - Markdown report + CSV generated under `scripts/rx/reports/`.

### Milestone 7 (Hardware Run) — 40/80/160 MHz Bandwidths, 6 GHz & RFK Calibrations
- Channel bandwidth tuning ported: MAC (`R_AX_WMAC_RFMOD`), BB (`R_FC0_BW`, `R_CHBW_MOD`,
  sampling delay / bandwidth select, 40MHz 2XFFT/GI), and RF (`_bw_setting`, `_set_rxbb_bw`,
  TIA bandwidth, `rfk.lck`). Validated live on silicon (40 MHz & 80 MHz on ch 36).
- 6 GHz band support (`RTW89_BAND_6G`, `R_MUIC` bit `B_MUIC_EN`, frequency `5950 + ch * 5`).
  Validated live on silicon (ch 1 @ 5955 MHz).
- RFK calibrations: `rfk.dack` executes S0 and S1 ADDCK DAC calibration; `rfk.iqk` and `rfk.dpk`
  dispatch H2C firmware offloads (`H2C_FUNC_RFK_IQK_OFFLOAD` and `H2C_FUNC_RFK_DPK_OFFLOAD`),
  accepted and executed by the WLAN CPU firmware.

### Milestone 8 (Hardware Run) — End-to-End Application Attack Injection
- Full top-level integration verified via `scripts/chips/rtl8852cu/test_attack.py`:
  - Discovered and claimed as `wlan0: RTL8852CU` via `DeviceManager`.
  - Initialized through the application's `WlanInterface` API.
  - Sniffed live APs with calibrated RSSI on channel 11.
  - Executed `iface.deauth_broadcast(target_bssid, count=16)`.
  - PMAC hardware counter `CCK_TXON` moved by exactly +16, proving end-to-end on-air radiation
    from application frame generation down to the PHY.

---

## 2. Key Findings & Critical Root Causes Resolved

1. **Baseband Gain Table Corruption Bug Resolved:**
   - In `phy.py`, `bb_gain_tbl.TABLE` was previously executed as register writes via `_config_bb_reg`.
   - In `rtw89` (`phy.c:1632`), this table is an array of packed `union rtw89_phy_bb_gain_arg` metadata structures.
   - Writing these entries directly caused hundreds of spurious writes to addresses `0x10000` (`R_UPD_P0`), `0x10001`, `0x20000`, etc., corrupting the baseband clock and ADC FIFO registers.
   - Fixed by implementing `BBGainInfo` and parsing entries into memory without touching hardware registers during table init.

2. **Missing `set_gain_error` LNA & TIA Calibration on Channel Tune:**
   - In Linux driver (`rtw8852c.c:1023`), `rtw8852c_set_gain_error` writes calibrated LNA 0-6 and TIA 0-1 gain steps on every channel tune.
   - Ported and wired into `phy.set_channel` for both 2.4 GHz and 5 GHz bands across Path A and Path B.

3. **Missing Path B CHIP_CAV Mirror Sequence:**
   - In `rtw8852c_rfk.c:3888`, Path B requires copying `RR_CFGCH` from Path A with `RR_APK` mode 3 and `RR_RSV1` reset toggle. Ported into `phy.set_channel`.

4. **Firmware Polling Timeout on USB:**
   - `_poll8` was converting `FWDL_WAIT_CNT_USB` (3,200) into microseconds, giving a timeout budget of only 3.2 milliseconds.
   - On USB, a single vendor control request takes 1–2 ms, causing premature poll timeouts.
   - Fixed by enforcing a minimum 2.0-second timeout window for USB polling.

5. **Hardware Power State Caveat:**
   - Executing `mac.power_switch(False)` (`pwr_off_func`) shuts off internal LDO and XTAL rails, causing the RTL8852CU to detach from the physical USB 3.0 bus (`0bda:c832` disappears from `lsusb`).
   - The device must remain powered or be physically replugged/power-cycled to re-appear on the bus.

---

## 3. What Remains to Implement (Pending Items)

### 3.1 Bulk-IN Endpoint `0x84` Live Frame Delivery — **DONE (2026-11-05)**
1. CRC counters confirmed real air traffic: `CCK_CRC ok+86 err+84`, `OFDM_CCA +545M` counts in 4 s.
2. PLE free-page counters moved (bank0 908–1812), proving frames entered the packet buffer.
3. End-to-end reception confirmed: 3182 bulk-IN transfers / 1.86 MB / 381 MPDUs in 4 s, and 166
   parsed packets delivered to the RX callback in the 5 s smoke test, listing AP SSIDs on
   2.4 GHz (ch 1/6/11) and 5 GHz (ch 36).

Root causes fixed (see `RTL8852CU.md` debug log for the citations):
- `B_AX_STOP_WPDMA` (`0x1010` bit 19) was never cleared — the AXI write-path DMA stayed halted.
- `SNIFFER_AX_RX_FLTR` was built from scratch instead of from `DEFAULT_AX_RX_FLTR`, dropping the
  broadcast and CAM-match bits that admit beacons.
- `B_AX_BCN_DROP_ALLOW` (`0xC400` bit 14) was never cleared.
- Stale H2C/C2H mailbox triggers from a previous session caused `0x7160`/`0x7164` poll timeouts.
- Repeat connects: no register distinguishes a cold ROM from live firmware, so `connect()` probes
  the mailbox and either downloads (cold) or re-attaches without touching the MAC (warm).

### 3.2 Milestone 5 — Frame Injection (Arbitrary TX) — **DONE (LIVE 2026-11-05)**
1. **TX Descriptor Engine (`src/wifit3/chips/rtl8852cu/tx.py`):**
   - `build_tx_desc_mgmt` ports `rtw89_core_fill_txdesc_v1` (`core.c:1494-1688`): 8 body dwords
     + 6 info dwords = **56 bytes** for the 8852C (`rtw8852c.c:3274-3275`), not the 40/48-byte
     v0 pair previously noted.
   - MGMT frame: macid 0, no security, `QSEL_B0_MGMT`, `ch_dma CH8`, CCK1/OFDM6 by band,
     `DISDATAFB`, RTS for unicast, USB `STF_MODE` bit.
   - Routed to `_mgmt_ep = out_pipe[BULKOUT_ID_B0MG]` (0x05 on this card).
2. **Driver Injection API:**
   - `_inject_frame` bulk-OUTs `desc + frame`; `_stamp_tx_seq` writes an incrementing 12-bit
     sequence so body3 `SW_SEQ` matches the frame.
   - Unit tests in `tests/chips/rtl8852cu/test_tx.py` (8 cases). Live TX not yet attempted.
3. **TX Power Chain — PORTED (2026-11-05), unit-tested:**
   - `phy.init_txpwr_unit` (called from `init_bb_reg`, `phy.c:1958`): `PWR_UL_CTRL2`/`COEXT_CTRL`/
     `UL_CTRL0`, UL TB offsets, and `init_tssi_ctrl` (flat bandedge), `rtw8852c.c:2305`.
   - `phy.set_txpwr_ref` (called from `_bring_up_mac_and_phy`, kernel `set_txpwr_ctrl` at
     `phy.c:8331`, and at the end of `phy.set_channel`): `R_AX_PWR_RATE_CTRL` plus the BB
     OFDM/CCK references on paths A/B, `rtw8852c.c:2114`.
   - `phy.power_trim` (kernel `phy.c:8332`): thermal (`RR_TM2`) and PA bias (`RR_BIASA`) from
     phycap, `rtw8852c.c:743-830`.
   - `phy.set_txpwr_byrate`: 11 dwords (`0xD2C0..0xD2E8`) por banda (2.4G / 5G) e offset de taxa
     zerado (`R_AX_PWR_RATE_OFST_CTRL` 0xD208), `rtw8852c_table.c:31371, phy.c:3142`.
   - `phy.set_txpwr_limit`: 20 dwords (`0xD2EC..0xD338`) uncapped com 0x3F3F3F3F, `phy.c:3227`.
   - `phy.set_txpwr_limit_ru`: 12 dwords (`0xD33C..0xD368`) uncapped com 0x3F3F3F3F, `phy.c:3262`.
   - `phy.set_txpwr`: orquestra byrate, limit, limit_ru e ref a cada troca de canal (`set_channel`).
   - Still not ported: RFE-dependent tx-shape e SAR diff.
   - `dack`, `dpk`, `iqk`, and `txgapk` from `rtw8852c_rfk.c` remain unported.
4. **Auditoria do caminho TX (2026-11-05) — nenhum bug no código novo:**
   - Descriptor conferido contra `rtw89_core_fill_txdesc_v1`: body0/2/3/7 e info0/4 batem
     (macid 0, `QMODE_STF`, `WD_INFO`, `WD_PAGE`, `STF_MODE`, `SW_SEQ`, `USE_RATE`,
     `DISDATAFB`, RTS só para unicast, `TXPKT_SIZE`).
   - Taxa e banda conferidas contra `rtw89_core_tx_update_injection` (`core.c:1226`): CCK1 em
     2.4 GHz, OFDM6 em 5 GHz, `USE_RATE` + `DISDATAFB` apenas — exatamente o caminho do kernel
     para `IEEE80211_TX_CTL_INJECTED`.
   - `h2c_default_cmac_tbl` está correto ao omitir `NTX_PATH_EN`/`PATH_MAP_*`: o kernel só os
     envia quando `h2c_cctl_func_id == H2C_FUNC_MAC_CCTLINFO_UD` (0x2); o 8852C usa `_UD_V1` (0xA).
   - B0/`CH8` em todas as bandas está correto: o chip é single-MAC (STF), as duas bandas rodam em
     MAC0; B1 (`out_pipe[1]`) não entra. (Correção de uma nota anterior.)
   - `enter_active_monitor` e `exit_active_monitor` implementados com `FAKE_MAC = FakeMacSupport.SPOOFABLE`:
     arma auto-ACK em hardware via H2C ADDR CAM (`firmware.h2c_addr_cam`) com SMA spoofado,
     e desfaz com `h2c_cam` (re-zero do SMA). Validado no silício real.
5. **Verificação no ar (2026-11-05) — PASSOU:**
   - `test_tx.py --channel 1`: 32 probe requests -> `CCK_TXON` +32.
   - `test_tx.py --channel 36`: 32 probe requests -> `OFDM_TXON` +32.
   - `test_tx.py --type data`: 16 frames de dados QoS-less (EAPOL shape) -> `CCK_TXON` +16 no ch 1 e `OFDM_TXON` +16 no ch 36.
   - Contadores PMAC são a prova de radiação (TX-on, não só bulk-OUT aceito). Rodou no caminho
     warm, então `init_txpwr_unit`/`power_trim` de cold-start seguem sem validação em hardware.

---

## 4. Quick Reference — Subsystem Map

| Subsystem | File | Core Functions / Registers |
|---|---|---|
| Power & Handshake | `mac.py`, `driver.py` | `pwr_on_func`, `connect()`, `R_AX_SYS_CFG1` |
| Transport & Registers | `transport.py` | `_vendorreq`, `read32`/`write32`, `read_xtal_si` |
| Firmware & Mailbox | `firmware.py` | `download()`, `h2c_command()`, `msg_reg()` |
| DMA & DLE/HFC Quotas | `trx.py` | `SCC_USB3_*`, `dle_init()`, `hfc_init()`, `is_usb3()` |
| PHY & Tuning | `phy.py`, `chan.py` | `init_bb_reg()`, `init_rf_reg()`, `set_channel()`, `set_gain_error()` |
| RF Calibrations | `rfk.py` | `rck()`, `lck()`, `rx_dck()` |
| Frame Demux | `rx.py` | `iter_bulk_frames()`, `parse_c2h_hdr()`, Bulk-IN `0x84` |
| Frame TX Injection | `tx.py` | `build_tx_desc_mgmt()`, AX v1 descriptor, Bulk-OUT `0x05` |
| Hardware Test Script | `scripts/chips/rtl8852cu/test_hw.py` | Live smoke validation |
| Diagnostic Script | `scripts/chips/rtl8852cu/diag_rx.py` | Live register & counter diagnostics |
