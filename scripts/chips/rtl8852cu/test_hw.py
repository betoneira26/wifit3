"""
Minimal RTL8852CU live bring-up smoke test.
Validates:
  1. USB device found (0bda:c832)
  2. chip-version read (control-IN sanity)
  3. connect() completes on physical hardware:
     - power_switch
     - firmware download (rtw8852c_fw-2.bin)
     - efuse dump and parse
     - phycap dump and parse
     - firmware phycap query (H2CREG / C2HREG)
     - MAC enable (enable_bb_rf, sys_init, trx_init, mac_post_init)
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


async def main(args):
    setup_logging(args.debug)

    step("USB Discovery")
    dev, did = _find_device()
    if dev is None:
        fail("RTL8852CU device not found. Ensure kernel driver is unbound.")
    speed = getattr(dev, "speed", None)
    ok(f"Found {did.vid:04x}:{did.pid:04x} at bus {dev.bus}, address {dev.address}, speed={speed}")

    driver = RTL8852CUDriver.from_usb_device(dev, did)

    step("chip-version read (control-IN sanity)")
    try:
        driver._claim_vendor_interface()
        cv = driver.read_chip_ver()
    except Exception as e:
        fail(f"chip-version read raised {type(e).__name__}: {e}")
    ok(f"cv=0x{cv:x}")

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
    ok("connect() succeeded: power + firmware + efuse + phycap + MAC + PHY tables + monitor bring-up")

    step("Channel Tuning")
    for test_ch in (6, 11, 36, 1):
        try:
            await driver.set_channel(test_ch)
            ok(f"set_channel({test_ch}) succeeded")
        except Exception as e:
            fail(f"set_channel({test_ch}) raised {type(e).__name__}: {e}")

    step("Live RX Capture (5 seconds on channel 11)")
    rx_frames = []

    def on_frame(frame):
        rx_frames.append(frame)
        ssid = getattr(frame, "ssid", None) or "<hidden>"
        bssid = getattr(frame, "bssid", None) or "N/A"
        rssi = getattr(frame, "rssi", None)
        rssi_str = f"{rssi}dBm" if rssi is not None else "N/A"
        subtype = getattr(frame, "type", "frame")
        if len(rx_frames) <= 10:
            print(f"  [RX #{len(rx_frames)}] {subtype}: bssid={bssid} ssid='{ssid}' rssi={rssi_str}")

    driver.register_rx_callback(on_frame)
    await driver.set_channel(11)
    t = driver.transport
    for sec in range(5):
        await asyncio.sleep(1.0)
        cca = t.read32(0x11A24)
        cck_crc = t.read32(0x11714)
        ofdm_crc = t.read32(0x11A64)
        ht_crc = t.read32(0x11A60)
        he_crc = t.read32(0x11A58)
        print(f"  [sec {sec+1}] CCA={cca} | CCK_CRC: OK={cck_crc & 0xFFFF} Fail={(cck_crc >> 16) & 0xFFFF} | OFDM_CRC: OK={ofdm_crc & 0xFFFF} Err={(ofdm_crc >> 16) & 0xFFFF} | HT_OK={ht_crc & 0xFFFF} HE_OK={he_crc & 0xFFFF} | Frames={len(rx_frames)}")
    print(f"Total frames captured in 5s: {len(rx_frames)}")

    step("Cleanup")
    await driver.close()
    print("\n=== RTL8852CU M1 + M2 + M3 + M4 PASSED ON LIVE SILICON ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTL8852CU live connect() smoke test")
    parser.add_argument("--debug", action="store_true", help="DEBUG-level logging")
    try:
        asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt:
        print("\n[ABORTED] Keyboard interrupt")
        sys.exit(1)
