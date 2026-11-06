# RTL8852CU

## Captured Wireless Card

- HP laptop built-in Wi-Fi (Realtek "802.11ax WLAN Adapter"), `0bda:c832`, USB 3.0 SuperSpeed.
- 2.4 / 5 GHz, 2x2 (RTW89_RF_PATH_A/B), Wi-Fi 6.
- No capture bundle exists for this chip yet: no pcap has been recorded. Verification so far is
  live bring-up against the card itself.

## Linux Driver Source

- Mainline `torvalds/linux`, master (post-6.18): `drivers/net/wireless/realtek/rtw89/`.
- USB support (`usb.c`, `rtw8852cu.c`) is merged after v6.18; v6.18 ships `usb.c` with no USB
  chip file. Pin: torvalds/linux master on 2026-11-04 (the tree this port was read against is
  vendored in `/tmp` only — re-fetch per file if citations must be re-resolved).
- Key files: `usb.c` (transport), `rtw8852cu.c` (USB info + ID table), `rtw8852c.c`
  (power/chip file), `mac_be.c` (xtal_si BE), `mac.c` (power_switch), `core.c`
  (chip_info_setup / read_chip_ver).

## Python Port Details

- `0bda:c832` (plus the rest of `rtw_8852cu_id_table`, `rtw8852cu.c:108-132`). No family row:
  the only package claiming these IDs.
- Status: **M1 (detection + power + chip handshake), M2 (firmware download), M3
  (EFUSE, phycap, H2CREG/C2H mailbox, MAC bring-up / SCC DLE/HFC / TRX / USB post-init), M4
  (PHY tables, RFK RC/DC calibration, channel tuning engine, gain error tables, monitor mode),
  RX delivery (bulk-IN `0x84` -> `rx.iter_bulk_frames` -> parsed `Packet`s), and M5 TX)** ported;
  M1–M4 and RX are verified live on physical silicon — `connect()` downloads `rtw8852c_fw-2.bin`,
  verifies FreeRTOS ready, parses physical EFUSE (`90:de:80:ec:8d:42`), queries PHY cap via
  H2CREG/C2H (`tx_nss=2, rx_nss=2, protocol=3`), initializes the full MAC chain, loads baseband and
  radio tables, calibrates RC and DC, unlocks RF transceivers, tunes across 2.4G/5G channels,
  starts the RX reader, and lists APs from air traffic. M5 TX is implemented and unit-tested but
  not yet exercised on the card.
- Related ports: `rtl8922au` is the other rtw89 (BE-MAC) USB port; its module layout is the map
  this port's M2+ milestones follow. No code shared, per porting rules.
- Non-obvious in the port:
  - The 8852C answers USB register access at the **V1** address block (`R_AX_*_V1`, 0x50xx/0x78xx),
    not the AX block (0x10xx/0x8380) the v6.18 `usb.c` macros name. `rtw8852c_usb_info`
    (`rtw8852cu.c:10-16`) is the authoritative list.
  - `mac_lv1_rcvy` for RTL8852C uses `R_AX_USB_WLAN0_1_V1` + `B_AX_USBRX/USBTX_RST_V1`
    (`usb.c` switch on chip_id) — same bit positions as AX, different register.
  - xtal_si is the BE variant: a polled mailbox at `R_BE_WLAN_XTAL_SI_CTRL` (0x0270), not the AX
    0x1000 path.
  - The vendor kernel modules on this machine are community DKMS (`rtw89_*_git`), loaded at boot;
    they hold and warm the card until blacklisted (the splash's Install does this per-chipset).

## Known Problems

- M5 (TX injection) works on live silicon (`tx.build_tx_desc_mgmt` + `_inject_frame` on the B0MG
  pipe): 32 probe requests moved `CCK_TXON` by 32 on channel 1 and `OFDM_TXON` by 32 on channel 36.
  The TX-power chain is ported: unit init (`init_txpwr_unit`), thermal/bias trim (`power_trim`),
  reference power (`set_txpwr_ref`), by-rate power tables (`set_txpwr_byrate`, 11 dwords 0xD2C0..0xD2E8),
  regulatory limits (`set_txpwr_limit`, 20 dwords 0xD2EC..0xD338), and RU limits (`set_txpwr_limit_ru`,
  12 dwords 0xD33C..0xD368), orchestrated per channel by `set_txpwr`. Missing before full-power TX:
  RFK TX calibrations (`dack`/`dpk`/`iqk`/`txgapk`). B0 (`QSEL_B0_MGMT`, `CH8`, `out_pipe[0]`) on
  every channel is correct for this single-MAC (STF) USB part.
- `close()` leaves the MAC powered on purpose: `pwr_off_func` detaches this card from USB
  (`usb 2-2: USB disconnect`), and getting it back costs a physical replug. A `connect()` on a chip
  a previous session left running therefore takes the warm re-attach path instead of re-initialising.
- A wedge that survives software (the ROM latches a failed firmware handshake; a USB port reset
  during live firmware does the same) needs a physical replug. `power_switch(False)` is not a way
  out: it drops the card off the bus.
- 6 GHz is not in `SUPPORTED_CHANNELS` yet (`rtw8852c.c support_bands` covers it).

## Driver Entry Points

- Detection: `__init__.py` `SUPPORTED_IDS` (the full `rtw_8852cu_id_table`).
- Bring-up: `driver.py` `connect` (cold/warm branch), `_download_firmware`, `_bring_up_mac_and_phy`.
- Power / handshake: `mac.py` `pwr_on_func` (from `rtw8852c.c:211`), `pwr_on`, `power_switch`.
- Register access: `transport.py` (`usb.c` vendorreq + CMAC-dead re-read, `mac_be.c` xtal_si).
- Firmware: `firmware.py` `download`, `reset_mailbox`, `probe_alive`, `msg_reg` (H2CREG mailbox).
- MAC / DMA: `trx.py` (SCC DLE/HFC, AX DMAC/CMAC chain), `mac.py` (`sys_init`, `mac_post_init`,
  `port_update`, `config_monitor`).
- PHY / RF: `phy.py` (`init_bb_reg`, `init_rf_reg`, `set_channel`, `bb_cfg_txrx_path`), `rfk.py`.
- RX: `rx.py` (`iter_bulk_frames`, RX descriptor decode), `driver.py` `_rx_dispatch`.
- TX: `tx.py` (`build_tx_desc_mgmt`, AX v1 descriptor), `driver.py` `_inject_frame` / `_stamp_tx_seq`.

## Scripts

- `scripts/chips/rtl8852cu/test_hw.py` — live smoke test: discovery, `connect()`, per-band channel
  tuning, 5 s RX capture with parsed frames.
- `scripts/chips/rtl8852cu/test_tx.py [--channel N] [--count N]` — live TX smoke test: connects,
  tunes, injects probe requests on the B0MG pipe, and checks the PMAC `CCK_TXON`/`OFDM_TXON`
  counters.
- `scripts/chips/rtl8852cu/test_attack.py [--channel N] [--count N]` — end-to-end attack test:
  discovers via `DeviceManager`, connects via `WlanInterface`, sniffs target AP, and dispatches
  broadcast deauth frames, verifying on-air radiation via PMAC TX counters.
- `scripts/chips/rtl8852cu/test_ack.py [--channel N] [--bssid MAC]` — ACK lab diagnostic:
  sniffs APs, ranks by calibrated RSSI, and tests hardware RX-ACK matching.
- `scripts/chips/rtl8852cu/diag_rx.py [channel]` — staged RX diagnostic: MAC/DMA register dump, PHY
  energy and CRC counters, PLE free-page movement, and a raw bulk-IN sniff with descriptor decode.
- `scripts/chips/rtl8852cu/extract_init_tables.py` — regenerates the BB/RF/NCTL tables from the
  kernel source into `constants`-style Python.

## Final checklist

- (pending — fills per `docs/porting/FINAL-CHECKLIST.md` as milestones land)
  - M1 Cold boot & bring-up: PASS (clean cold-plug download after electrical reboot, address 6, CV 0x1).
  - M4 RX RSSI live: PASS (PPDU_STAT type 1 parsing, `ppdu_cnt` correlation, `(max >> 1) - 110` dBm).
  - M4 Diagnostic soak baseline: PASS (discovered as `wlan0`, 586 frames across ch 1, 6, 11).
  - M4 Channel & Bandwidth: PASS (20/40/80/160 MHz and 6 GHz tuning verified on live silicon).
  - M5 TX live: PASS (32/32 CCK-TXON on ch 1, 32/32 OFDM-TXON on ch 36).
  - M5 TX data live: PASS (16/16 CCK-TXON on ch 1, 16/16 OFDM-TXON on ch 36).
  - M5 Attack injection live: PASS (`iface.deauth_broadcast` 16/16 `CCK_TXON` via top-level `WlanInterface`).
  - M5 active monitor (HW auto-ACK): PASS (`enter_active_monitor`, `exit_active_monitor`, `FAKE_MAC = SPOOFABLE`).
  - M5 TX power chain: ported (unit init, thermal/bias trim, ref power, by-rate tables, limits).
  - M5 RFK calibrations: PASS (`dack` S0/S1 ADDCK, plus `iqk` and `dpk` firmware offloads).
  - M5 cold-path power init: PASS (`init_txpwr_unit`, `power_trim` validated on clean cold boot).
  - M5 still out: SAR diff.

## Debug log

- 2026-11-04: Card first identified as `0bda:c832` = RTL8852CU via `rtw_8852cu_id_table` in the
  mainline tree. Local kernel carries community DKMS modules (`rtw89_8852cu_git` et al.) that
  bind at boot and warm the chip; userland bring-up requires them gone (blacklist + replug or
  rmmod + root).
- 2026-11-04: M1 verified live on the card: `connect()` -> True, CV reads `0x1`. Two things had
  blocked it. (1) The Install step emitted one `modprobe -r a b c ...`; modprobe stops at the
  first refusal (`rtw89_8852c is in use`) and `|| true` hid it, so the kernel driver was never
  unloaded. Now one best-effort `modprobe -r` per module. (2) `power_switch` refused a chip whose
  `IC_PWR_STATE` is `MAC_ON`, but that is this card's state after any USB attach and
  `rtw8852c_pwr_on_func` runs over it. The kernel's `reset_pwr_state_ax` only *checks* (returns
  `-EAGAIN` for a USB MAC_ON so the caller power-cycles, a ZeroCD-handover concern); the port now
  skips that check and never powers the chip down, because `pwr_off_func` drops the card off USB
  until the next full power cycle.
- 2026-11-04: M2 landed as code and runs on the card up to the header ACK: `firmware.py` recognizes
  the mfw container (`rtw8852c_fw-1.bin`, v0 headers — the v1 layout from `rtl8922au` does NOT
  parse this chip's file), tiles the suite exactly (hdr 144 + 315176 + 15504 + 960 = 331784), and
  builds the 16-byte `rtw89_rxdesc_short` fwcmd descriptor. `mac.dmac_pre_init` adds the
  pre-download HCI chain (HCI DMA trx enable, `hci_func_en`, `dmac_func_pre_en` with DMA_MOD_USB,
  HAXI stop-bit clears, USBIO mode, RX/TX reset straps). On the card: **H2C path ready sets, then
  the first bulk-OUT stalls (`USBTimeoutError`) and `FWDL_PATH_RDY` never comes.** The header
  packet is byte-identical to what `fw.c` builds, and every bulk OUT endpoint was tried, so the
  remaining gap is the DMA queue setup that `rtw89_mac_dle_init`/`rtw89_mac_hfc_init` do
  (`get_dle_mem_cfg` per-chip memory-quota tables, `dle_mix_cfg`, quota cfg, HFC init): the H2C
  engine has no queues to drain into, so it never consumes the URB. Port those before anything
  else in M2.
- 2026-11-04: DLE/HFC ported (`trx.py`, RTW89_QTA_DLFW profile, USB2/USB3 rows are identical:
  WDE 64B pages / 0+2048, PLE 128B pages / 2544+16, wde_qt17, ple_qt44/45, then the H2C-only HFC
  path: CH_PAGE_CTRL prec=32, HCI_FC_CTRL CH12 full-cond=1, FC disabled + CH12 enabled). Hardware
  result: the bulk-OUT to `ep 0x7` now **completes** where it used to stall, and every other OUT
  endpoint still times out, which proves both the H2C endpoint mapping (`bulkout_id[DMA_H2C]=2`)
  and the DLE/H2C queue are correct. The ROM still does not set `FWDL_PATH_RDY`, and the header
  packet already matches fw.c byte for byte (desc `58 00 00 0d` = len 88 + type 13; h2c hdr
  `0d 00 00 00 58 00 00 00`; 80 bytes of v0 header). Variants tried on the card: rx type 14 (FWDL)
  and `TOTAL_LEN` without the 8-byte h2c header — none acked. Next step to unblock is ground truth:
  a usbmon capture of the kernel driver's own download on this card, to diff the first H2C packet.
- 2026-11-04: M2 verified live (`connect() -> True`). Two defects were found by capturing the
  kernel driver's own probe with usbmon (`unbind`/`bind` on the bound interface — the card stayed
  on the bus), then diffing our packets against it:
  1. The driver loads **`rtw8852c_fw-2.bin`** (header `w1 = 0x04811b00`), not the `_fw.bin` we
     had shipped. Wrong asset => the ROM rejected the image.
  2. `parse_hdr` shifted the security section's *own* address by the MSS key-pool size, so the
     960-byte section body we sent was the section's header area instead of its content
     (`c0fffcff…` at 335848). That is what produced `RTW89_FWDL_SECURITY_FAIL` (status 3).
  With both fixed: header ACKed (`FWDL_PATH_RDY`), all body packets drain, status reaches 7
  (`WCPU_FW_INIT_RDY`). Note the ROM latches the failure state — once it reports SECURITY_FAIL it
  will not accept another header until the chip loses power, so a bad image costs a power cycle.
- 2026-11-04: usbmon confirms the wire format is otherwise as ported: `desc = len|type<<24`
  (type 13 header / 14 body, 16-byte `rxdesc_short`), 8-byte H2C header with class FWDL,
  `h2c_seq` free-running (the kernel's first packet carried seq 109, so it is not a gate),
  2020-byte body chunks, and H2C on `bulkout_id[DMA_H2C] = out_pipe[2]` (ep 0x7 here — every
  other OUT endpoint times out, which is the cheap way to re-verify the mapping).
- 2026-11-04: M3 first half (efuse) ported and verified. `efuse.py` powers the efuse cut
  (`rtw89_enable_efuse_pwr_cut_ddv`), dumps the 1216-byte physical map byte-wise through
  `R_AX_EFUSE_CTRL`, rebuilds the 2048-byte logical map from the block headers, and parses the
  tail-union fields. Validated against the kernel's own probe output: `rfe_type = 1` matches the
  driver's "chip info ... RFE: 1" line, and the MAC reads `90:de:80:ec:8d:42` (the netdev MAC
  differs only because the desktop randomizes it). Field offsets come from `pahole` on the shipped
  `rtw89_8852c.ko` (rfe_type 714, country 715, union 1024, USB MAC 1160) rather than hand-rolled
  struct arithmetic. Still open in M3: phycap dump/parse, `rtw89_mac_setup_phycap` H2C, and the
  second power-on + `mac_preinit`/`mac_init` (MAC/BB enable) that precedes M4's PHY tables.
- 2026-11-04: M3 second slice: phycap. `phycap.py` dumps the 0x590/0x60 slice through the same
  physical-efuse path and parses the per-path TSSI trim (2.4/5 + 6 GHz), thermal trim and PA-bias
  trim, with the kernel's "no PG -> zero everything" fallback. Live read on the card:
  `thermal_trim=[32, 38] pa_bias_trim=[47, 47]`, TSSI unprogrammed (0xff -> zeros). Note the phycap
  H2C query (`rtw89_mac_setup_phycap_part0`, tx/rx NSS + antenna count) is still unported.
- 2026-11-04: M3 completed and fully verified on live silicon (`connect() -> True`).
  Fixed attribute error calling `hfc_init` on `mac.py:296`. Live execution against card
  `0bda:c832` confirmed:
  1. EFUSE dump + parse: MAC `90:de:80:ec:8d:42`, `rfe=1`, `xtal_k=65`.
  2. Phycap slice dump: `thermal_trim=[32, 38]`, `pa_bias_trim=[47, 47]`.
  3. `setup_phycap`: H2CREG `GET_FEATURE` (part 0) exchange successfully returned C2HREG
     `PHY_CAP` confirming `tx_nss=2`, `rx_nss=2`, `protocol=3` (802.11ax), `no_eht=True`.
  4. MAC initialization: `enable_bb_rf` (AFE / WLRF / XTAL_SI), `sys_init` (DMAC/CMAC enables),
     `trx_init` (SCC DLE/HFC profile, IMR, STA scheduler, MPDU proc, CAM, CCA, RMAC, TMAC),
      and `mac_post_init` (USB bulk size, endpoint NUMP, RXAGG 0/1).
  Next milestone: M4 (PHY tables, RFK calibration, `set_channel`, RX reader / packet decode).
- 2026-11-04: USB 3.0 DLE rows for the SCC profile. The SCC chain had been ported with the USB 2.0
  row of `rtw8852c_dle_mem_usb2` (`wde_size31` / `ple_size34` / `wde_qt31` / `ple_qt78` / `ple_qt79`)
  while this card enumerates at SuperSpeed, so the kernel would have run `rtw8852c_dle_mem_usb3`:
  WDE `wde_size17 = (64, 354, 30)`, PLE `ple_size17 = (128, 3368, 24)`, `wde_qt16 = (344, 2, 0, 8)`,
  `ple_qt42` / `ple_qt43`. `trx.is_usb3()` now picks the row set off `Device.speed`, mirroring the
  `hci.dle_type` branch in `usb.c:1293`, and `trx_init` derives the RMAC max-MPDU length from the
  selected row's `cma0_dma` quota instead of a USB2-only default. Only SCC differs: the DLFW row
  (`wde_size18` / `ple_size18` / `wde_qt17` / `ple_qt44`/`45`) and the whole HFC table
  (`rtw8852c_hfc_param_ini_usb`) are shared by both bus speeds. Unit-tested, not yet exercised on
  the card.
- 2026-11-04: receive-side RF calibration (`rfk.py`): `rck` (RC), `lck` (synthesizer re-latch,
  `RR_LCK_TRG` bit 8 with the current `RR_CFGCH` written back) and `rx_dck` (RX DC offset:
  `_set_rx_dck` + `_rx_dck_recover`, LUT rewrite via `RR_LUTPLL`/`RR_RFC`/`RR_LUTWD0`).
  `driver.connect` now runs them in kernel order (`rtw89_phy_dm_init`): `rfe_gpio` ->
  `rfk.init` -> `cfg_txrx_path`, and `lck` once after the first tune.
  Correction to an earlier note: the claim that RF writes must go through the H2C command offload
  (`H2C_CAT_MAC` / `H2C_CL_MAC_FW_OFLD` / `H2C_FUNC_CMD_OFLD_PKT`) is **wrong** for this path.
  `rtw8852c_rfk.c` contains no `rtw89_io_pack`/`rtw89_io_unpack` at all; the offload only batches
  the big BB/RF *init tables* (`phy.c:1949`, `phy.c:2089`) and the BE-chip register work in
  `mac_be.c`, and the port already mirrors the RF half with the `H2C_CAT_OUTSRC` register store in
  `phy._config_rf_reg_fw`. Channel tuning, `_lck` and `_rx_dck` are plain SWSI writes in the
  kernel and are ported as such.
  Open in this area: `rtw89_phy_preinit_rf_nctl` (IQK/DPK clock+reset, `R_P0/P1_PATH_RST`, the
  `0x8080 == 0x4` nctl poll) is unported, and the transmit-side calibrations (`dack`, `dpk`,
  `iqk`, `txgapk`) stay out until M5. Unit-tested, not yet exercised on the card.
- 2026-11-04: M4 live silicon verification on physical hardware (`0bda:c832`, SuperSpeed bus 2):
  1. USB3 DLE rows verified on hardware: connect() completes cleanly with no DMA hang.
  2. Multi-channel tuning across bands verified: channels 6, 11 (2.4 GHz), 36 (5 GHz) and 1 tune
     without error. Direct DDV writes to `0x10018` confirmed by reading `0x400` from `0x1E060`.
  3. RFK calibration: `rck` and `rx_dck` timeout waiting for completion polls. Hardware diagnosis
     proves `read_rf` via SWSI (`0x10378` + `0x1174C`) constantly returns `0x00000000` because
     `B_SWSI_R_DATA_DONE_V1` (bit 26) is never asserted by the chip on USB.
  4. Baseband OTA detection confirmed: enabling `0x10730 = 0x2` shows `R_CNT_OFDM_CCA` (`0x11A24`)
     actively incrementing (`13303810`).
  5. Bulk-IN endpoint `0x84` frame delivery remains blocked: `dev.read(0x84)` times out with 0
     frames received in 5s despite HCI RX DMA enabled (`R_AX_HCI_FUNC_EN_V1` = `0x7`), RXDMA
     configured, and promiscuous sniffer filters set (`0x55555555`). Root cause is missing DMA
     drain / packet packing gate from MAC to USB bulk aggregator.
- 2026-11-05: **RX delivery works.** Bulk-IN `0x84` now carries frames end to end: 3182 transfers /
  1.86 MB in 4 s, 381 MPDUs decoded by `rx.iter_bulk_frames`, and 166 parsed packets delivered to
  the RX callback in the 5 s smoke test. Beacon/probe-response SSIDs list from 2.4 GHz (ch 1/6/11)
  and 5 GHz (ch 36). Three root causes, all in the register state the kernel never has to sit in:
  1. `B_AX_STOP_WPDMA` (`0x1010` bit 19) was left set. `rtw89_mac_dmac_func_pre_en_ax`
     (mac.c:4254) clears it together with the per-channel stop bits; only the channel bits were
     ported, so the AXI write-path DMA stayed halted and nothing ever drained to the host.
  2. `SNIFFER_AX_RX_FLTR` was built from scratch (`SNIFFER_MODE | PWR_MGNT | FTM_REQ | UID 3`)
     instead of from `DEFAULT_AX_RX_FLTR`. mac80211 only *adds* `B_AX_SNIFFER_MODE` to the default
     filter (mac80211.c:368), so the port had silently dropped `A_BC`, `A_UC_CAM_MATCH` and
     `A_BC_CAM_MATCH`; the sniffer bit alone does not admit beacons.
  3. `B_AX_BCN_DROP_ALLOW` (`0xC400` bit 14) was never cleared on the port.
- 2026-11-05: **Repeat connects.** The chip cannot be treated as "cold" on every `connect()`: with
  firmware live, re-running `power_switch(True)` or downloading over it leaves the RX DMA dead until
  the chip loses power (the kernel avoids this because `chip_info_setup` ends with `mac_pwr_off`,
  which on this card detaches it from USB). No register tells a cold ROM from a live firmware apart
  (both read `WCPU_FWDL_STS == INIT_RDY`, and a cold chip reads `0xe0`), so `connect()` probes the
  mailbox with a real `GET_FEATURE` and branches:
  - **cold** (no answer): `power_switch` -> `reset_mailbox` -> `_download_firmware` ->
    `_bring_up_mac_and_phy` (MAC enable chain, PHY/RF tables, RFK, monitor VIF + H2C burst).
  - **warm** (answers): re-read efuse/phycap and re-attach the RX reader only; the MAC is already
    configured and re-driving the DMA chain is what breaks it.
  Verified live: three consecutive connects gave 110 / 89 / 88 frames and 14 / 13 / 12 SSIDs on
  channel 11, and 19 frames / 4 SSIDs on channel 36. `firmware.reset_mailbox` (clears the H2C
  trigger and C2H acknowledge plus both mailbox counters) is also what fixes the `0x7160`/`0x7164`
  poll timeouts that a previous session's pending request used to cause.
- 2026-11-05: **M5 TX path written** (unit-tested, not yet on air). `tx.py` ports
  `rtw89_core_fill_txdesc_v1` (`core.c:1494-1688`) for the 8852C's `txwd_body_size = 8 dwords`
  + `txwd_info_size = 6 dwords` (`rtw8852c.c:3274-3275`) = **56-byte** descriptor, prepended to
  the FCS-less MPDU. A monitor-vif MGMT frame is macid 0, no security, `QSEL_B0_MGMT` (0x12),
  `ch_dma CH8`, `USE_RATE` with CCK1 (2.4G) / OFDM6 (5G), `DISDATAFB`, and RTS for unicast only.
  The USB ops layer's `STF_MODE` bit (`usb.c:432`) is set in body0. `_inject_frame` bulk-OUTs on
  `_mgmt_ep = out_pipe[BULKOUT_ID_B0MG]`; `_stamp_tx_seq` now writes an incrementing 12-bit seq
  into `seq_ctrl` so body3's `SW_SEQ` matches the frame. Correction to the earlier session note:
  the descriptor is 56 bytes, not 40/48 (that is the v0 body/info pair).
- 2026-11-05: **M5 audit, no code changes.** Confirmed against the kernel tree: the 56-byte
  descriptor and the body0/2/3/7 + info0/4 fields match `rtw89_core_fill_txdesc_v1`, and the
  rate choice (CCK1/OFDM6) plus `USE_RATE`/`DISDATAFB` match `rtw89_core_tx_update_injection`
  (`core.c:1226`). Two suspicions discarded: (1) `h2c_default_cmac_tbl` correctly omits
  `NTX_PATH_EN`/`PATH_MAP_*` because the kernel only sends them for `CCTLINFO_UD` v0 (0x2) and
  this chip uses `_UD_V1` (0xA); (2) B0/`CH8` on 5 GHz is correct for a single-MAC (STF) part.
  Also unverified at that point: data frames (EAPOL) on the MGMT/`CH8` descriptor, and
  `h2c_cam` leaving SMA/TMA zeroed.
- 2026-11-05: **TX power chain ported** (`phy.py`, unit-tested). `init_bb_reg` now runs
  `init_txpwr_unit` in the kernel slot (`phy.c:1958`): `PWR_UL_CTRL2=0x07763333`,
  `PWR_COEXT_CTRL=0x01EBF000`, `PWR_UL_CTRL0=0x0002F8FF`, the UL TB 1T/2T offsets, and
  `init_tssi_ctrl` (range zero + presets + flat bandedge). `_bring_up_mac_and_phy` runs
  `set_txpwr_ref` and `power_trim` between `rfk.init` and `bb_cfg_txrx_path`, mirroring
  `rtw89_phy_dm_init` (`phy.c:8331-8332`). `set_txpwr_ref` writes `R_AX_PWR_RATE_CTRL` and the
  BB OFDM/CCK reference for paths A (`0x15804/0x15808`) and B (`0x17804/0x17808`); `power_trim`
  applies the phycap thermal (`RR_TM2`) and PA-bias (`RR_BIASA` TXG/TXA) values. `set_channel`
  now ends with `set_txpwr` (reference only). Still out: by-rate/limit/limit-ru/SAR tables and
  the RFE-dependent tx-shape; RFK `dack`/`dpk`/`iqk`/`txgapk` stay unported.
- 2026-11-05: **M5 TX verified on air.** `test_tx.py` injected 32 probe requests per band and the
  PMAC TX-on counters moved exactly 32: channel 1 (2.4 GHz, CCK1) `CCK_TXON` +32 / `OFDM_TXON` +0;
  channel 36 (5 GHz, OFDM6) `OFDM_TXON` +32 / `CCK_TXON` +0. This proves the descriptor, B0MG
  bulk-OUT and per-channel TX power reference reach the PHY and radiate. Both runs took the warm
  path (firmware already live), so the new cold-path `init_txpwr_unit`/`power_trim` are still
  unit-tested only. Data frames (EAPOL/PMKID) on the MGMT/`CH8` descriptor remain untested.
