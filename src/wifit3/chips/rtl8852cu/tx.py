"""RTL8852CU TX: build the rtw89 AX v1 TX descriptor for a management frame.

The descriptor is 8 body dwords + 6 info dwords = 56 bytes, prepended to the FCS-less MPDU (the
hardware appends the FCS). A monitor-vif MGMT frame is macid 0, no security, QSEL B0_MGMT,
ch_dma CH8, lowest basic rate. [SRC] core.c:1494-1688 fill_txdesc_v1, txrx.h:69-149, core.h:1278,
rtw8852c.c:3114,3274."""
import struct

HW_RATE_CCK1 = 0x0
HW_RATE_OFDM6 = 0x4
QSEL_B0_MGMT = 0x12
TXCH_CH8 = 8
BULKOUT_ID_B0MG = 0
TXWD_BODY_SIZE = 32
TXWD_INFO_SIZE = 24


def build_tx_desc_mgmt(mpdu: bytes, *, band_is_2g: bool = True) -> bytes:
    """rtw89_core_fill_txdesc_v1 for a monitor-vif MGMT frame. The descriptor's SW_SEQ mirrors the
    MPDU's seq_ctrl, and RTS is requested for unicast only. [SRC] core.c:902-935,1494-1688."""
    seq = (int.from_bytes(mpdu[22:24], "little") >> 4) & 0xFFF if len(mpdu) >= 24 else 0
    is_bmc = len(mpdu) >= 5 and (mpdu[4] & 0x01)
    rate = HW_RATE_CCK1 if band_is_2g else HW_RATE_OFDM6
    w = [0] * 14
    w[0] = (1 << 22) | (TXCH_CH8 << 16) | (1 << 10) | (1 << 7)
    w[2] = (QSEL_B0_MGMT << 17) | (len(mpdu) & 0x3FFF)
    w[3] = seq
    w[7] = (1 << 31) | ((rate & 0x1FF) << 16)
    w[8] = 1 << 10
    w[12] = (1 << 31) | (0 if is_bmc else (1 << 27))
    return struct.pack("<14I", *w)
