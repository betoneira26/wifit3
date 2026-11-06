"""
RTL8852CU ACK lab.

Finds a real AP on the tuned channel, injects unicast probe requests to its BSSID with a
chosen source MAC, and counts the returning ACKs through the RX tap.

    uv run scripts/chips/rtl8852cu/test_ack.py --channel 6 --count 100

The chip's monitor filter already admits ACK control frames, so `_enable_rx_acks` is a no-op
and the tally works purely off `record_ack`. Success = the AP pointed its ACK at our TA.
"""
import argparse
import asyncio
import logging
import sys
from collections import defaultdict
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


def _mac_bytes(mac_str: str) -> bytes:
    return bytes.fromhex(mac_str.replace(":", ""))


def _probe_to(bssid: bytes, src: bytes, ssid: str = "") -> bytes:
    frame = bytearray(b"\x40\x00\x00\x00")
    frame += bssid                    # addr1: the AP
    frame += src                      # addr2: our TA
    frame += bssid                    # addr3
    frame += b"\x00\x00"              # seq_ctrl (driver stamps)
    ie = ssid.encode("utf-8", "replace")[:32]
    frame += bytes([0x00, len(ie)]) + ie
    return bytes(frame)


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

    stats = defaultdict(lambda: {"count": 0, "rssi": -127, "ssid": ""})

    def on_frame(pkt):
        bssid = pkt.bssid
        if not bssid or bssid == "ff:ff:ff:ff:ff:ff":
            return
        s = stats[bssid]
        s["count"] += 1
        if pkt.rssi is not None:
            s["rssi"] = max(s["rssi"], pkt.rssi)
        if pkt.ssid:
            s["ssid"] = pkt.ssid

    driver.register_rx_callback(on_frame)

    step(f"Sniffing {args.scan}s for APs")
    await asyncio.sleep(args.scan)

    src = _mac_bytes(driver.mac_address)
    if args.bssid:
        target_bssid_str = args.bssid.lower()
        bssid = _mac_bytes(target_bssid_str)
        ssid = stats[target_bssid_str]["ssid"] if target_bssid_str in stats else ""
        print(f"  target BSSID explicitly set: {target_bssid_str} ({ssid!r}), source TA {driver.mac_address}")
        ok("BSSID set by argument")
    else:
        if not stats:
            fail("no beacons/probe responses heard; pick another channel")

        ranked = sorted(stats.items(), key=lambda kv: (kv[1]["count"], kv[1]["rssi"]), reverse=True)
        print(f"  {len(ranked)} BSSIDs heard; top:")
        for b, s in ranked[:5]:
            print(f"    {b}  rssi={s['rssi']:4d}  frames={s['count']:4d}  ssid={s['ssid']!r}")

        target_bssid_str, best = ranked[0]
        bssid = _mac_bytes(target_bssid_str)
        ssid = best["ssid"]
        print(f"  target BSSID {target_bssid_str} ({ssid!r}), source TA {driver.mac_address}")
        ok("BSSID picked")

    step("Arm ACK tally")
    await driver.enable_rx_acks()
    ok("tally armed")

    step(f"Inject {args.count} unicast probe requests")
    frame = _probe_to(bssid, src, ssid)
    sent = 0
    for _ in range(args.count):
        if not await driver.inject_frame(frame):
            fail(f"inject_frame returned False after {sent} frames")
        sent += 1
        await asyncio.sleep(args.interval)
    await asyncio.sleep(0.1)
    acks = driver.acks_seen(src)
    ok(f"{sent} frames sent")

    step("Result")
    ratio = acks / sent if sent else 0.0
    print(f"  ACKs seen: {acks}/{sent} ({ratio:.1%})")
    await driver.disable_rx_acks()
    await driver.close()

    if acks > 0:
        ok(f"ACK lab: {acks}/{sent} from {target_bssid_str}")
        print("\n=== RTL8852CU RX-ACK TALLY WORKS ===")
        return True
    fail("no ACKs seen; check RX filter or that the AP is alive")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTL8852CU ACK lab")
    parser.add_argument("--channel", type=int, default=6)
    parser.add_argument("--bssid", type=str, default=None, help="Target BSSID (xx:xx:xx:xx:xx:xx)")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--scan", type=float, default=3.0)
    parser.add_argument("--interval", type=float, default=0.01)
    parser.add_argument("--debug", action="store_true", help="DEBUG-level logging")
    try:
        asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt:
        print("\n[ABORTED] Keyboard interrupt")
        sys.exit(1)
