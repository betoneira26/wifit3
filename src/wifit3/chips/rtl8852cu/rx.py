"""RTL8852CU RX: split a bulk-IN transfer into 802.11 MPDUs, stripping the rtw89 AX rx descriptor.

One bulk-IN transfer carries N packets, each a fixed rx descriptor (16B short / 32B long) plus
shift/drv-info, then the MPDU (FCS-inclusive). Packets are 8-byte aligned (rtw8852cu rx_agg_alignment).
pkt_type 0 (WIFI) is an 802.11 frame; pkt_type 10 is C2H firmware report.
[SRC] core.c:4143 query_rxdesc, usb.c:477, rtw8852cu.c:18.
"""
import struct

RX_RECVBUF_SZ = 20480                    # RTW89_USB_RECVBUF_SZ. usb.h:14
RX_TYPE_WIFI = 0                         # RTW89_CORE_RX_TYPE_WIFI. core.h:389
RX_TYPE_PPDU_STAT = 1                    # RTW89_CORE_RX_TYPE_PPDU_STAT. core.h:390
RX_TYPE_C2H = 10                         # RTW89_CORE_RX_TYPE_C2H. core.h:399
_RX_TYPE_WIFI = RX_TYPE_WIFI


def parse_c2h_hdr(payload: bytes):
    """(category, class, func) from a C2H packet's 8-byte header, or None if too short."""
    if len(payload) < 8:
        return None
    w0 = struct.unpack_from("<I", payload, 0)[0]
    return w0 & 0x3, (w0 & 0xFC) >> 2, (w0 & 0xFF00) >> 8


def iter_bulk_frames(buf: bytes, state: dict | None = None):
    """Yield (pkt_type, payload, rssi) per packet in a bulk-IN transfer.
    For WIFI (pkt_type 0) payload is the FCS-stripped 802.11 MPDU; for C2H (pkt_type 10)
    payload is the firmware report. PPDU status reports (pkt_type 1) supply the RSSI.
    [SRC] core.c:2270-2279, 4143-4195, core.h:226, usb.c:477-505."""
    pos, n = 0, len(buf)
    if state is None:
        state = {"ppdu": {}, "last_rssi": None}
    ppdu_map = state.setdefault("ppdu", {})

    # Pre-scan PPDU_STAT reports in this transfer to map ppdu_cnt -> rssi_dbm
    while pos + 16 <= n:
        w0 = struct.unpack_from("<I", buf, pos)[0]
        long_rxdesc = (w0 >> 31) & 1
        rxd_len = 32 if long_rxdesc else 16
        pkt_size = w0 & 0x3FFF
        shift_len = ((w0 >> 14) & 0x3) << 1
        drv_info_len = ((w0 >> 28) & 0x7) << 3
        pkt_type = (w0 >> 24) & 0xF
        mpdu_off = rxd_len + shift_len + drv_info_len
        total = mpdu_off + pkt_size
        if pkt_size == 0 or pos + total > n:
            break
        if pkt_type == RX_TYPE_PPDU_STAT and pos + mpdu_off + 8 <= n:
            s0, s1 = struct.unpack_from("<2I", buf, pos + mpdu_off)
            if s0 & (1 << 7):                              # RTW89_PHY_STS_HDR_W0_VALID [SRC] txrx.h:467, core.c:2292
                w1 = struct.unpack_from("<I", buf, pos + 4)[0]
                ppdu_cnt = (w1 >> 4) & 0x7
                rssi_avg = (s0 >> 24) & 0xFF
                rssi_a = s1 & 0xFF
                rssi_b = (s1 >> 8) & 0xFF
                raw = max(rssi_a, rssi_b) or rssi_avg
                if raw:
                    dbm = min((raw >> 1) - 110, -1)        # RTW89_RSSI_RAW_TO_DBM [SRC] core.h:226
                    ppdu_map[ppdu_cnt] = dbm
                    state["last_rssi"] = dbm
        pos += (total + 7) & ~7

    # Main pass: deliver WIFI and C2H frames
    pos = 0
    while pos + 16 <= n:
        w0 = struct.unpack_from("<I", buf, pos)[0]
        long_rxdesc = (w0 >> 31) & 1
        rxd_len = 32 if long_rxdesc else 16
        pkt_size = w0 & 0x3FFF
        shift_len = ((w0 >> 14) & 0x3) << 1
        drv_info_len = ((w0 >> 28) & 0x7) << 3
        pkt_type = (w0 >> 24) & 0xF
        mpdu_off = rxd_len + shift_len + drv_info_len
        total = mpdu_off + pkt_size
        if pkt_size == 0 or pos + total > n:
            break
        if pkt_type == RX_TYPE_WIFI:
            w1 = struct.unpack_from("<I", buf, pos + 4)[0]
            ppdu_cnt = (w1 >> 4) & 0x7
            rssi = ppdu_map.get(ppdu_cnt, state.get("last_rssi"))
            mpdu = bytes(buf[pos + mpdu_off:pos + mpdu_off + max(pkt_size - 4, 0)])
            yield RX_TYPE_WIFI, mpdu, rssi
        elif pkt_type == RX_TYPE_C2H:
            yield RX_TYPE_C2H, bytes(buf[pos + mpdu_off:pos + mpdu_off + pkt_size]), None
        pos += (total + 7) & ~7
