"""Unit tests for RTL8852CU RX parser."""
import struct
from wifit3.chips.rtl8852cu.rx import iter_bulk_frames, RX_TYPE_WIFI, RX_TYPE_C2H


def test_short_rxdesc_wifi_frame():
    # 16-byte short descriptor for WIFI frame, pkt_size = 20 (16 bytes MPDU + 4 bytes FCS)
    pkt_size = 20
    pkt_type = 0
    dword0 = pkt_size | (pkt_type << 24)
    rxd = struct.pack("<IIII", dword0, 0, 0, 0)
    payload = b"A" * 16 + b"FCS!"
    buf = rxd + payload
    # Add 8-byte alignment padding
    buf += b"\x00" * ((8 - len(buf) % 8) % 8)

    frames = list(iter_bulk_frames(buf))
    assert len(frames) == 1
    t, mpdu, rssi = frames[0]
    assert t == RX_TYPE_WIFI
    assert mpdu == b"A" * 16
    assert rssi is None


def test_c2h_frame():
    pkt_size = 8
    pkt_type = 10
    dword0 = pkt_size | (pkt_type << 24)
    rxd = struct.pack("<IIII", dword0, 0, 0, 0)
    c2h_data = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    buf = rxd + c2h_data
    buf += b"\x00" * ((8 - len(buf) % 8) % 8)

    frames = list(iter_bulk_frames(buf))
    assert len(frames) == 1
    t, data, rssi = frames[0]
    assert t == RX_TYPE_C2H
    assert data == c2h_data


def test_wifi_frame_with_ppdu_stat_rssi():
    # 1. PPDU_STAT packet (type 1), pkt_size = 16, ppdu_cnt = 3
    # s0: valid bit (1 << 7), rssi_avg = 140 (140 >> 1 - 110 = -40 dBm)
    # s1: rssi_a = 140, rssi_b = 100
    pkt_size_stat = 16
    pkt_type_stat = 1
    d0_stat = pkt_size_stat | (pkt_type_stat << 24)
    d1_stat = 3 << 4  # ppdu_cnt = 3
    rxd_stat = struct.pack("<IIII", d0_stat, d1_stat, 0, 0)
    s0 = (1 << 7) | (140 << 24)
    s1 = 140 | (100 << 8)
    stat_payload = struct.pack("<IIII", s0, s1, 0, 0)
    buf_stat = rxd_stat + stat_payload
    buf_stat += b"\x00" * ((8 - len(buf_stat) % 8) % 8)

    # 2. WIFI packet (type 0), ppdu_cnt = 3
    pkt_size_wifi = 20
    d0_wifi = pkt_size_wifi | (0 << 24)
    d1_wifi = 3 << 4  # ppdu_cnt = 3
    rxd_wifi = struct.pack("<IIII", d0_wifi, d1_wifi, 0, 0)
    wifi_payload = b"B" * 16 + b"FCS!"
    buf_wifi = rxd_wifi + wifi_payload
    buf_wifi += b"\x00" * ((8 - len(buf_wifi) % 8) % 8)

    frames = list(iter_bulk_frames(buf_stat + buf_wifi))
    assert len(frames) == 1
    t, mpdu, rssi = frames[0]
    assert t == RX_TYPE_WIFI
    assert mpdu == b"B" * 16
    assert rssi == -40


def test_ppdu_stat_invalid_bit_ignored():
    # PPDU_STAT with valid bit = 0
    d0_stat = 16 | (1 << 24)
    d1_stat = 3 << 4
    rxd_stat = struct.pack("<IIII", d0_stat, d1_stat, 0, 0)
    s0 = (0 << 7) | (140 << 24)  # valid = 0!
    stat_payload = struct.pack("<IIII", s0, 0, 0, 0)
    buf_stat = rxd_stat + stat_payload
    buf_stat += b"\x00" * ((8 - len(buf_stat) % 8) % 8)

    d0_wifi = 20 | (0 << 24)
    d1_wifi = 3 << 4
    rxd_wifi = struct.pack("<IIII", d0_wifi, d1_wifi, 0, 0)
    buf_wifi = rxd_wifi + b"C" * 16 + b"FCS!"
    buf_wifi += b"\x00" * ((8 - len(buf_wifi) % 8) % 8)

    frames = list(iter_bulk_frames(buf_stat + buf_wifi))
    assert len(frames) == 1
    assert frames[0][2] is None
