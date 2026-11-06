"""
RTL8852CU live TX smoke test.

Connects in monitor mode, tunes to a channel, injects probe requests through the M5 path
(AX v1 descriptor + bulk-OUT on B0MG), and checks the PMAC TX-on counters for movement.

    uv run scripts/chips/rtl8852cu/test_tx.py --channel 1 --count 32

The counters are BB registers (rtw89_phy_read32 adds the 0x10000 CR base):
  CCK_TXON  0x1704 -> 0x11704   (probe at CCK1 on 2.4 GHz)
  OFDM_TXON 0x1A40 -> 0x11A40   (probe at OFDM6 on 5 GHz)
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import libusb_package
import usb.core

from wifit3.chips.rtl8852cu import SUPPORTED_IDS
from wifit3.chips.rtl8852cu.driver import RTL8852CUDriver

CONNECT_TIMEOUT = 90
CCK_TXON = 0x11704
OFDM_TXON = 0x11A40


def setup_logging(debug: bool):
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def step(label: str):
    print(f"\n--- {label} ---")


def ok(msg: str):
    print(f"[PASS] {msg}")


def fail(msg: str):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _find_device():
    backend = libusb_package.get_libusb1_backend()
    for did in SUPPORTED_IDS:
        dev = usb.core.find(idVendor=did.vid, idProduct=did.pid, backend=backend)
        if dev is not None:
            return dev, did
    return None, None


def _probe_request(src: bytes = b"\x02\x11\x22\x33\x44\x55") -> bytes:
    frame = bytearray(b"\x40\x00\x00\x00")
    frame += b"\xff" * 6              # addr1: broadcast
    frame += src                      # addr2
    frame += b"\xff" * 6              # addr3: broadcast
    frame += b"\x00\x00"              # seq_ctrl (driver stamps)
    frame += b"\x00\x00"              # wildcard SSID IE
    return bytes(frame)


def _eapol_data(src: bytes = b"\x02\x11\x22\x33\x44\x55") -> bytes:
    """QoS-less data frame carrying LLC/SNAP + an EAPOL-Key header (PMKID shape)."""
    frame = bytearray(b"\x08\x01\x00\x00")   # data, ToDS
    frame += b"\xff" * 6                      # addr1: broadcast (no ACK)
    frame += src                              # addr2
    frame += b"\xff" * 6                      # addr3
    frame += b"\x00\x00"                      # seq_ctrl (driver stamps)
    frame += b"\xaa\xaa\x03\x00\x00\x00\x88\x8e"  # LLC/SNAP, EAPOL ethertype
    frame += b"\x02\x03\x00\x05"              # EAPOL v2, key, length 5
    frame += b"\x01\x00\x00\x00\x00"
    return bytes(frame)


def _read_counters(t):
    return {
        "cck_txon": t.read32(CCK_TXON) & 0xFFFF,
        "ofdm_txon": t.read32(OFDM_TXON) & 0xFFFF,
    }


async def main(args):
    setup_logging(args.debug)

    step("USB Discovery")
    dev, did = _find_device()
    if dev is None:
        fail("RTL8852CU device not found. Ensure the kernel driver is unbound.")
    ok(f"Found {did.vid:04x}:{did.pid:04x} at bus {dev.bus}, address {dev.address}")

    driver = RTL8852CUDriver.from_usb_device(dev, did)

    step(f"connect() [{CONNECT_TIMEOUT}s timeout]")
    try:
        success = await asyncio.wait_for(
            driver.connect(progress_cb=lambda p, m: print(f"  [{p*100:5.1f}%] {m}")),
            timeout=CONNECT_TIMEOUT,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        fail(f"connect() raised {type(e).__name__}: {e}")
    if not success:
        fail("connect() returned False")
    ok("connect() succeeded")

    step(f"Channel {args.channel}")
    await driver.set_channel(args.channel)
    ok(f"tuned to {args.channel}")

    t = driver.transport
    before = _read_counters(t)
    print(f"  before: {before}")

    step(f"Inject {args.count} {args.type} frames")
    frame = _eapol_data() if args.type == "data" else _probe_request()
    sent = 0
    for _ in range(args.count):
        if not await driver.inject_frame(frame):
            fail(f"inject_frame returned False after {sent} frames")
        sent += 1
        await asyncio.sleep(args.interval)
    ok(f"{sent} frames bulk-OUT on the B0MG pipe")

    after = _read_counters(t)
    delta = {k: after[k] - before[k] for k in after}
    print(f"  after:  {after}")
    print(f"  delta:  {delta}")

    step("Cleanup")
    await driver.close()

    if max(delta.values()) > 0:
        ok(f"TX counters moved: {delta}")
        print("\n=== RTL8852CU M5 TX PASSED ON LIVE SILICON ===")
        return True
    fail("TX counters did not move; frame reached the DMA but did not radiate")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTL8852CU live TX smoke test")
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--type", choices=("mgmt", "data"), default="mgmt")
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--debug", action="store_true", help="DEBUG-level logging")
    try:
        asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt:
        print("\n[ABORTED] Keyboard interrupt")
        sys.exit(1)
