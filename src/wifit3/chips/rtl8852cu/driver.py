"""RTL8852CU driver: Realtek RTL8852C (802.11ax) over USB, ported from the mainline
rtw89 tree (master, post-6.18 — USB support post-v6.18). See RTL8852CU.md.

Status: M1-M5 and RX are ported from the same source tree; M5 TX is unit-tested,
not yet live-verified. See RTL8852CU.md.
"""
import asyncio
import logging
from typing import Callable, ClassVar, Optional

import usb.core
import usb.util

from wifit3.dot11.parser import WlanFrameParser
from wifit3.errors import BringUpError

from ..driver import Driver, DeviceID, ProgressCallback, FakeMacSupport
from ..rx_reader import RxReaderThread
from . import chan, efuse, firmware, mac, phy, phycap, rfk, rx, tx
from .constants import (
    R_AX_SYS_CFG1, B_AX_CHIP_VER_MASK,
    BULKOUT_ID_H2C, BULKOUT_ID_B0MG,
)
from .transport import RTL8852CUTransport

logger = logging.getLogger(__name__)


class RTL8852CUDriver(Driver):
    """Realtek RTL8852C (802.11ax) USB driver, ported from the rtw89 mainline source."""

    # 2.4 GHz + 5 GHz at 20 MHz, non-DFS. The 8852C also does 6 GHz (rtw8852c.c
    # support_bands) — unported until the chip file lands.
    SUPPORTED_CHANNELS = (
        list(range(1, 15))
        + [36, 40, 44, 48, 149, 153, 157, 161, 165]
    )

    FAKE_MAC: ClassVar[FakeMacSupport] = FakeMacSupport.SPOOFABLE

    CONFLICTING_LINUX_MODULES: ClassVar = [
        "rtw89_8852cu", "rtw89_usb", "rtw89_core", "rtw89_8852c", "rtw89_pci"]

    def __init__(self) -> None:
        super().__init__()
        self.dev: Optional[usb.core.Device] = None
        self.transport: Optional[RTL8852CUTransport] = None
        self.mac: Optional[mac.RTL8852CUMac] = None
        self._rx_cb: Optional[Callable] = None
        self._disconnect_cb: Optional[Callable[[Exception], None]] = None
        self._h2c_ep: Optional[int] = None
        self._mgmt_ep: Optional[int] = None
        self._bulk_in_ep: Optional[int] = None
        self._rx_reader: Optional[RxReaderThread] = None
        self._intf: Optional[int] = None
        self._tx_seq: int = 0
        self._band_is_2g: bool = True
        self.mac_address: Optional[str] = None
        self.efuse: Optional[dict] = None
        self.phycap: Optional[dict] = None
        self._active_mac: Optional[bytes] = None
        self._rx_state: dict = {"ppdu": {}, "last_rssi": None}
        self.is_warm = False

    @classmethod
    def from_usb_device(cls, dev: usb.core.Device, id_entry: DeviceID) -> "RTL8852CUDriver":
        self = cls()
        self.dev = dev
        self.transport = RTL8852CUTransport(dev)
        self.mac = mac.RTL8852CUMac(self.transport)
        return self

    def register_rx_callback(self, cb: Callable) -> None:
        self._rx_cb = cb

    def register_disconnect_callback(self, cb: Callable[[], None]) -> None:
        self._disconnect_cb = cb

    def _claim_vendor_interface(self) -> Optional[int]:
        """Claim the vendor-specific (class 0xFF) interface that owns the bulk endpoints.
        [SRC] usb.c rtw89_usb_parse: one bulk-IN, bulk-OUTs in descriptor order."""
        try:
            cfg = self.dev.get_active_configuration()
        except usb.core.USBError:
            # A card that a kernel-driver unload or a warm reset left unconfigured still
            # enumerates; re-set config 1 and read the descriptors again.
            self.dev.set_configuration()
            cfg = self.dev.get_active_configuration()
        for intf in cfg:
            if intf.bInterfaceClass != 0xFF:
                continue
            try:
                if self.dev.is_kernel_driver_active(intf.bInterfaceNumber):
                    self.dev.detach_kernel_driver(intf.bInterfaceNumber)
            except (NotImplementedError, usb.core.USBError):
                pass
            usb.util.claim_interface(self.dev, intf.bInterfaceNumber)
            self._discover_pipes(intf)
            return intf.bInterfaceNumber
        return None

    def _discover_pipes(self, intf) -> None:
        """Map DMA channels to bulk-OUT endpoints: out_pipe is the interface's bulk-OUT
        endpoint addresses in order; the H2C channel uses out_pipe[bulkout_id[DMA_H2C]].
        [SRC] usb.c rtw89_usb_parse/write_port, rtw8852cu.c:17-27 (bulkout_id[DMA_H2C]=2)."""
        out_pipe = [ep.bEndpointAddress for ep in intf
                    if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
                    and usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK]
        if len(out_pipe) > BULKOUT_ID_H2C:
            self._h2c_ep = out_pipe[BULKOUT_ID_H2C]
        if len(out_pipe) > BULKOUT_ID_B0MG:
            self._mgmt_ep = out_pipe[BULKOUT_ID_B0MG]     # B0MG queue = out_pipe[0]
        in_pipe = [ep.bEndpointAddress for ep in intf
                   if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN
                   and usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK]
        if in_pipe:
            self._bulk_in_ep = in_pipe[0]

    def read_chip_ver(self) -> int:
        """rtw89_read_chip_ver's CV read (the M1 silicon handshake). [SRC] core.c:5939-5943."""
        return self.transport.read32_mask(R_AX_SYS_CFG1, B_AX_CHIP_VER_MASK)

    def _download_firmware(self, cv: int) -> None:
        """The firmware path: DMAC pre-init, CPU off, FWDL enable, transfer the suit.
        [SRC] mac.c:4310-4345 rtw89_mac_partial_init."""
        firmware.reset_mailbox(self.transport)
        self.mac.dmac_pre_init()
        self.mac.disable_cpu()
        self.mac.enable_cpu_fwdl()
        firmware.download(self.transport, self._h2c_ep, cv)
        logger.info("RTL8852CU: firmware downloaded, FreeRTOS ready")

    async def connect(self, progress_cb: Optional[ProgressCallback] = None) -> bool:
        """Bring the chip to a monitor-mode RX state.
        [SRC] usb.c rtw89_usb_probe, core.c rtw89_chip_info_setup. Cold and warm chips take
        different paths: a cold one needs power-on, firmware and the whole MAC/PHY chain, while a
        chip a previous session left running is already configured and only needs its RX reattached."""
        self._intf = self._claim_vendor_interface()
        if self._intf is None:
            raise BringUpError("discover", "no vendor-specific (0xFF) interface found")
        # No register tells a cold ROM from a live firmware apart (both report INIT_RDY), so probe
        # the mailbox itself. A live firmware owns a fully configured MAC: powering it on again, or
        # downloading over it, leaves the RX DMA dead until the chip loses power.
        firmware.reset_mailbox(self.transport)
        self.is_warm = firmware.probe_alive(self.transport)
        if self.is_warm:
            logger.info("RTL8852CU: warm chip, firmware already live")
        elif not self.mac.power_switch(True):
            raise BringUpError("power", "power-on sequence timed out (PMC FSM / pwr_on_func)")
        cv = self.read_chip_ver()
        logger.info("RTL8852CU: chip cv=%x (warm=%s)", cv, self.is_warm)
        if not self.is_warm:
            self._download_firmware(cv)
        # M3 (first half): efuse. The MAC/RFE come from the logical map; both feed later RF setup.
        if not efuse.autoload_ok(self.transport):
            raise BringUpError("efuse", "efuse autoload did not complete")
        self.efuse = efuse.parse(efuse.logical_map(efuse.dump_physical(self.transport)))
        self.phycap = phycap.parse(phycap.dump(self.transport))
        self.mac_address = self.efuse["mac_addr_str"]
        logger.info("RTL8852CU: efuse mac=%s rfe=%d country=%s xtal_k=%d",
                    self.mac_address, self.efuse["rfe_type"], self.efuse["country_code"],
                    self.efuse["xtal_k"])
        logger.info("RTL8852CU: phycap thermal_trim=%s pa_bias_trim=%s",
                    self.phycap["thermal_trim"], self.phycap["pa_bias_trim"])
        # M3: firmware PHY capability (NSS / antennas / protocol) via the H2CREG mailbox.
        self.hal = self.mac.setup_phycap()
        logger.info("RTL8852CU: phycap hal tx_nss=%d rx_nss=%d tx_ant=0x%x rx_ant=0x%x "
                    "protocol=%d no_eht=%s",
                    self.hal["tx_nss"], self.hal["rx_nss"], self.hal["antenna_tx"],
                    self.hal["antenna_rx"], self.hal["protocol"], self.hal["no_eht"])
        self.transport.rfe_type = self.efuse["rfe_type"]
        if not self.is_warm:
            self._bring_up_mac_and_phy(cv)

        # Default to channel 1
        await self.set_channel(1)
        # The kernel re-latches the synthesizer from its thermal tracker (rtw8852c_lck_track); a
        # monitor bring-up has no tracker, so lock once after the first tune.
        rfk.lck(self.transport)

        # Start background bulk-IN receiver
        self._start_rx_reader()
        logger.info("RTL8852CU: RX reader thread started on ep 0x%02x", self._bulk_in_ep)
        return True

    def _bring_up_mac_and_phy(self, cv: int) -> None:
        """Everything a cold chip needs after its firmware: the MAC enable chain, the PHY/radio
        tables with RFK, and the monitor VIF with its H2C burst. A warm chip already carries all of
        it, and re-running the DMA chain under live firmware loses the RX path."""
        # M3: MAC bring-up. Kernel order in rtw89_mac_init: enable_bb_rf -> sys_init ->
        # trx_init (SCC DLE/HFC + AX DMAC/CMAC chain) -> feat_init (no-op for 8852C) ->
        # usb mac_post_init. [SRC] mac.c:4330-4390, usb.c:886.
        self.mac.enable_bb_rf()
        self.mac.sys_init()
        self.mac.trx_init()
        self.mac.mac_post_init()
        logger.info("RTL8852CU: MAC initialised (SCC DLE/HFC, TRX, USB post-init)")

        # M4: PHY layer tables + radio tuning + monitor mode
        # Kernel order in rtw89_phy_dm_init:
        #   1. init_bb_reg (including bb_reset)
        #   2. init_rf_reg (Radio B, then Radio A)
        #   3. btc_init
        #   4. bb_sethw (EVM reporting + GPIO TRSW switch routing)
        #   5. init_nctl_reg (preinit + table)
        #   6. rfk.init (RC + RX DC calibration)
        #   7. set_txpwr_ref (TX power unit reference)
        #   8. power_trim (thermal + PA bias)
        #   9. bb_cfg_txrx_path (antenna RX routing & MCS limits)
        phy.init_bb_reg(self.transport, cv)
        phy.init_rf_reg(self.transport, self._h2c_ep, cv)
        phy.btc_init(self.transport)
        phy.bb_sethw(self.transport)
        phy.init_nctl_reg(self.transport, cv)
        rfk.init(self.transport)
        phy.set_txpwr_ref(self.transport)
        phy.power_trim(self.transport, self.phycap)
        phy.bb_cfg_txrx_path(self.transport)
        logger.info("RTL8852CU: PHY tables (BB, RF A/B, NCTL), RFK (RC + RX DC), TX power "
                    "reference/trim, TX/RX paths, and BTC/antenna routing configured")

        # M4: monitor VIF and routing
        self.mac.port_update()
        self.mac.config_monitor()
        firmware.h2c_macid_pause(self.transport, self._h2c_ep, sh=0, grp=0, pause=False)
        firmware.h2c_role_maintain(self.transport, self._h2c_ep, macid=0, wifi_role=7)
        firmware.h2c_join_info(self.transport, self._h2c_ep, macid=0, wifi_role=7, dis_conn=True)
        firmware.h2c_cam(self.transport, self._h2c_ep)
        firmware.h2c_default_cmac_tbl(self.transport, self._h2c_ep, macid=0)
        firmware.h2c_fw_log(self.transport, self._h2c_ep, enable=False)
        logger.info("RTL8852CU: monitor mode and MAC filter configured")

    def _start_rx_reader(self) -> None:
        if self._bulk_in_ep is None:
            logger.warning("RTL8852CU: no bulk-IN endpoint; RX disabled")
            return
        self._rx_reader = RxReaderThread(
            asyncio.get_running_loop(), self._rx_read_once, self._rx_dispatch,
            name="rtl8852cu-rx",
            on_fatal=lambda e: self._disconnect_cb(e) if self._disconnect_cb else None,
        )
        self._rx_reader.start()

    def _rx_read_once(self) -> Optional[bytes]:
        try:
            buf = bytes(self.dev.read(self._bulk_in_ep, rx.RX_RECVBUF_SZ, 100))
            if buf:
                logger.debug("RTL8852CU: received bulk-IN buffer len=%d", len(buf))
            return buf
        except usb.core.USBError as e:
            err = getattr(e, "errno", None)
            if err in (110, 10060) or "timeout" in str(e).lower():
                return None
            raise

    def _rx_dispatch(self, buf: bytes) -> None:
        cb = self._rx_cb
        if not cb and not self._ack_detect_on:
            return
        for pkt_type, mpdu, rssi in rx.iter_bulk_frames(buf, state=self._rx_state):
            if pkt_type != rx.RX_TYPE_WIFI:
                continue
            if len(mpdu) == 10 and mpdu[0] == 0xD4:
                self.record_ack(mpdu)
                continue
            if not cb:
                continue
            parsed = WlanFrameParser.parse_80211_frame(mpdu, rssi if rssi is not None else -100)
            if parsed:
                try:
                    cb(parsed)
                except Exception:
                    logger.exception("RTL8852CU RX callback raised")

    async def set_channel(self, channel: int, scan: bool = False, *,
                          band: int | None = None, bandwidth: int = 0) -> bool:
        if band is None and channel not in self.SUPPORTED_CHANNELS:
            raise ValueError(f"Channel {channel} not supported")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: chan.set_channel(self.transport, channel, band=band, bandwidth=bandwidth))
        self.channel = channel
        self._band_is_2g = (band == 0) if band is not None else (channel <= 14)
        return True

    async def close(self) -> None:
        """Release the interface, leaving the MAC powered. `pwr_off_func` drops the 8852CU off the
        USB bus (observed: `usb 2-2: USB disconnect`), and the card is a built-in with no replug,
        so powering it down costs a full power cycle to get back. The next connect() resets the
        power state instead, so staying powered is the recoverable state."""
        if self._rx_reader is not None:
            await self._rx_reader.stop()
            self._rx_reader = None
        if self._intf is not None and self.dev is not None:
            try:
                usb.util.release_interface(self.dev, self._intf)
            except (usb.core.USBError, ValueError):
                pass
            self._intf = None

    async def _inject_frame(self, frame_bytes: bytes) -> bool:
        """Prepend the AX v1 mgmt TX descriptor and bulk-OUT the frame once on the B0MG pipe."""
        if self._mgmt_ep is None:
            logger.error("RTL8852CU inject_frame: no mgmt bulk-OUT endpoint (not connected?)")
            return False
        desc = tx.build_tx_desc_mgmt(frame_bytes, band_is_2g=self._band_is_2g)
        payload = desc + frame_bytes
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.transport.bulk_out(self._mgmt_ep, payload))
            return True
        except usb.core.USBError as e:
            logger.error("RTL8852CU inject_frame: bulk-OUT failed: %s", e)
            return False

    def _stamp_tx_seq(self, frame_bytes: bytes) -> bytes:
        """Write an incrementing 12-bit sequence into seq_ctrl so the on-air seq matches body3."""
        if len(frame_bytes) < 24:
            return frame_bytes
        self._tx_seq = (self._tx_seq + 1) & 0xFFF
        stamped = bytearray(frame_bytes)
        stamped[22:24] = ((self._tx_seq << 4) & 0xFFFF).to_bytes(2, "little")
        return bytes(stamped)

    async def _enable_rx_acks(self) -> None:
        return

    async def _disable_rx_acks(self) -> None:
        return

    async def enter_active_monitor(self, mac: bytes,
                                   bssid: Optional[bytes] = None) -> bytes:
        """Arm HW auto-ACK for ``mac``: the card ACKs any frame whose addr1 equals the SMA we put in
        addr-cam entry 0. [SRC] cam.c:768,819."""
        if self._h2c_ep is None:
            raise RuntimeError("RTL8852CU enter_active_monitor: not connected")
        sma = bytes(mac)
        tma = bytes(bssid) if bssid is not None else b"\x00" * 6
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: firmware.h2c_addr_cam(
                self.transport, self._h2c_ep, sma=sma, tma=tma,
                net_type=0, bssid=tma,
                bssid_mask=0x3F))
        self._active_mac = sma
        return sma

    async def exit_active_monitor(self) -> None:
        """Re-zero the addr-cam SMA (the connect-time h2c_cam baseline) so the responder stops
        auto-ACKing."""
        if self._h2c_ep is None:
            return
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: firmware.h2c_cam(self.transport, self._h2c_ep))
        self._active_mac = None
