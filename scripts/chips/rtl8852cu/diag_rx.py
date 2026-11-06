"""Stage-by-stage RX diagnostic: PHY energy, demod CRC, MAC/DMA config, bulk-IN delivery.

Run with the RTL8852CU plugged in and its kernel driver unloaded:
    uv run python scripts/chips/rtl8852cu/diag_rx.py [channel]
"""
import asyncio
import sys

import libusb_package
import usb.core

from wifit3.chips.rtl8852cu import SUPPORTED_IDS
from wifit3.chips.rtl8852cu import constants as C
from wifit3.chips.rtl8852cu.driver import RTL8852CUDriver
from wifit3.chips.rtl8852cu.rx import RX_RECVBUF_SZ, iter_bulk_frames

CR_BASE_AX = 0x10000

CNT_CCK_CCA = CR_BASE_AX + 0x1710
CNT_CCK_CRC32 = CR_BASE_AX + 0x1714
CNT_OFDM_CCA = CR_BASE_AX + 0x1A24
CNT_HE_CRC = CR_BASE_AX + 0x1A58
CNT_VHT_CRC = CR_BASE_AX + 0x1A5C
CNT_HT_CRC = CR_BASE_AX + 0x1A60
CNT_L_CRC = CR_BASE_AX + 0x1A64
CNT_AMPDU_RX_CRC32 = CR_BASE_AX + 0x1A80

COUNTERS = (
    ("CCK_CCA", CNT_CCK_CCA),
    ("CCK_CRC32", CNT_CCK_CRC32),
    ("OFDM_CCA", CNT_OFDM_CCA),
    ("HE_CRC", CNT_HE_CRC),
    ("VHT_CRC", CNT_VHT_CRC),
    ("HT_CRC", CNT_HT_CRC),
    ("L_CRC", CNT_L_CRC),
    ("AMPDU_RX_CRC32", CNT_AMPDU_RX_CRC32),
)

MAC_STATE = (
    ("HCI_FUNC_EN_V1", C.R_AX_HCI_FUNC_EN_V1),
    ("HAXI_INIT_CFG1", C.R_AX_HAXI_INIT_CFG1),
    ("HAXI_DMA_STOP1", C.R_AX_HAXI_DMA_STOP1),
    ("HAXI_DMA_STOP2", C.R_AX_HAXI_DMA_STOP2),
    ("DMAC_FUNC_EN", C.R_AX_DMAC_FUNC_EN),
    ("CMAC_FUNC_EN", C.R_AX_CMAC_FUNC_EN),
    ("WDE_INI_STATUS", C.R_AX_WDE_INI_STATUS),
    ("PLE_INI_STATUS", C.R_AX_PLE_INI_STATUS),
    ("RX_FLTR_OPT", C.R_AX_RX_FLTR_OPT),
    ("CTRL_FLTR", C.R_AX_CTRL_FLTR),
    ("MGNT_FLTR", C.R_AX_MGNT_FLTR),
    ("DATA_FLTR", C.R_AX_DATA_FLTR),
    ("RCR", C.R_AX_RCR),
    ("PORT_CFG_P0", 0xC400),
    ("RXDMA_SETTING", C.R_AX_RXDMA_SETTING),
    ("RXAGG_0_V1", C.R_AX_RXAGG_0_V1),
    ("RXAGG_1_V1", C.R_AX_RXAGG_1_V1),
    ("PUB_PAGE_INFO1_V1", C.R_AX_PUB_PAGE_INFO1_V1),
    ("PUB_PAGE_INFO2_V1", C.R_AX_PUB_PAGE_INFO2_V1),
    ("PUB_PAGE_INFO3_V1", C.R_AX_PUB_PAGE_INFO3_V1),
)

CRC_OK_ERR = {"HE_CRC", "VHT_CRC", "HT_CRC", "L_CRC", "AMPDU_RX_CRC32", "CCK_CRC32"}

R_AX_PLE_DBG_FUN_INTF_CTL = 0x9110
R_AX_PLE_DBG_FUN_INTF_DATA = 0x9114
PLE_FREEPG_SEL = 0x80000000
R_AX_HAXI_DMA_BUSY1 = 0x101C
R_AX_PLE_QTA6_CFG = 0x9058


def ok(counter: str, val: int) -> int:
    return (val & 0xFFFF) if counter in CRC_OK_ERR else val


def err(counter: str, val: int) -> int:
    return (val >> 16) & 0xFFFF if counter in CRC_OK_ERR else 0


async def sample(t, seconds: float):
    first = {name: t.read32(addr) for name, addr in COUNTERS}
    await asyncio.sleep(seconds)
    last = {name: t.read32(addr) for name, addr in COUNTERS}
    return {name: (first[name], last[name]) for name in first}


def ple_free_pages(t) -> tuple:
    """Free-page counters for the two PLE banks via the PLE debug port. [SRC] debug.c:2551."""
    t.write32(R_AX_PLE_DBG_FUN_INTF_CTL, PLE_FREEPG_SEL)
    v = t.read32(R_AX_PLE_DBG_FUN_INTF_DATA)
    return v & 0xFFFF, (v >> 16) & 0xFFFF


async def track_ple(t, seconds: float):
    """Sample the PLE free-page counters: movement means frames are entering/leaving the buffer."""
    samples = []
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        samples.append(ple_free_pages(t))
        await asyncio.sleep(0.1)
    return samples


async def sniff(driver, seconds: float):
    loop = asyncio.get_running_loop()
    buffers = []
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        try:
            buf = await loop.run_in_executor(
                None, driver.dev.read, driver._bulk_in_ep, RX_RECVBUF_SZ, 500)
        except usb.core.USBError as e:
            if getattr(e, "errno", None) in (110, 10060):
                continue
            raise
        if buf:
            buffers.append(bytes(buf))
    return buffers


def verdict(deltas) -> str:
    cca = deltas["CCK_CCA"][1] + deltas["OFDM_CCA"][1]
    crc_ok = sum(ok(n, d[1]) for n, d in deltas.items() if n in CRC_OK_ERR)
    crc_err = sum(err(n, d[1]) for n, d in deltas.items() if n in CRC_OK_ERR)
    if cca == 0:
        return "sem energia em banda: PHY nao esta demodulando (ADC/CCA ou canal errado)"
    if crc_ok == 0 and crc_err == 0:
        return "energia detectada, nenhum PLCP decodificado: RX do BB ou limiares de PLCP"
    if crc_ok == 0:
        return f"PLCP decodificado mas {crc_err} CRCs invalidos: sincronismo/demod"
    return f"{crc_ok} MPDUs com CRC ok: o MAC/DMA e o proximo suspeito"


async def main():
    channel = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    backend = libusb_package.get_libusb1_backend()
    dev = None
    did = SUPPORTED_IDS[0]
    for did in SUPPORTED_IDS:
        dev = usb.core.find(idVendor=did.vid, idProduct=did.pid, backend=backend)
        if dev is not None:
            break
    if not dev:
        print("device not found (0bda:c832 off the bus)")
        return

    driver = RTL8852CUDriver.from_usb_device(dev, did)
    driver._claim_vendor_interface()
    await driver.connect()
    if driver._rx_reader is not None:
        await driver._rx_reader.stop()
        driver._rx_reader = None
    await driver.set_channel(channel)
    t = driver.transport
    print(f"\n=== tuned to channel {channel} ===")

    print("\n--- MAC / DMA state ---")
    for name, addr in MAC_STATE:
        print(f"  {name:20s} 0x{addr:04X} = 0x{t.read32(addr):08X}")

    print("\n--- counters over 4s ---")
    deltas, samples = await asyncio.gather(sample(t, 4.0), track_ple(t, 4.0))
    for name, (a, b) in deltas.items():
        d = b - a
        if name in CRC_OK_ERR:
            print(f"  {name:16s} ok+{ok(name, d):<8d} err+{err(name, d):<8d} (raw 0x{b:08X})")
        else:
            print(f"  {name:16s} +{d:<10d} (raw 0x{b:08X})")
    print("\n  veredito:", verdict(deltas))

    bank0 = [s[0] for s in samples]
    bank1 = [s[1] for s in samples]
    print(f"\n--- PLE free pages over 4s ({len(samples)} samples) ---")
    print(f"  bank0 min={min(bank0)} max={max(bank0)} (delta {bank0[-1] - bank0[0]})")
    print(f"  bank1 min={min(bank1)} max={max(bank1)} (delta {bank1[-1] - bank1[0]})")
    print("  qta6 (cma0_dma/RX):", hex(t.read32(R_AX_PLE_QTA6_CFG)))
    print("  HAXI_DMA_BUSY1:", hex(t.read32(R_AX_HAXI_DMA_BUSY1)))
    ple_moved = max(bank0) != min(bank0) or max(bank1) != min(bank1)
    print("  ->", "frames entrando no PLE" if ple_moved
          else "nada entra no PLE: o RMAC nao esta entregando ao buffer")

    print("\n--- bulk-IN 0x%02x for 4s ---" % driver._bulk_in_ep)
    buffers = await sniff(driver, 4.0)
    print(f"  {len(buffers)} transfers, {sum(len(b) for b in buffers)} bytes")
    frames = 0
    for buf in buffers:
        for pkt_type, payload, _ in iter_bulk_frames(buf):
            if pkt_type == 0:
                frames += 1
    print(f"  {frames} MPDUs parsed")
    if buffers:
        print("  first transfer:", buffers[0][:64].hex())

    await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
