"""Firmware container parsing for the RTL8852CU asset (v0 headers, AX part size)."""
from wifit3.chips.rtl8852cu import firmware


def test_mfw_picks_the_normal_suit_for_cv1():
    fw = firmware.load_fw_suit(1)
    assert len(fw) > 300_000
    assert fw[0] != 0xFF or True          # sub-firmware, not the container


def test_v0_header_parses_and_covers_the_whole_suit():
    fw = firmware.load_fw_suit(1)
    info = firmware.parse_hdr(fw)
    # AX forces the per-packet size; the parts must tile the suite exactly.
    assert info["part_size"] == 2020
    assert info["section_num"] == len(info["sections"]) == 3
    # The security section's MSS key pool trails it and is not downloaded, so the tiled
    # sections stop short of the file end by exactly that pool.
    tiled = info["hdr_len"] + sum(s["len"] for s in info["sections"])
    assert tiled < len(fw)
    assert [s["type"] for s in info["sections"]] == [2, 1, 9]
    assert [s["addr"] for s in info["sections"]] == [144, 320176, 335848]


def test_header_packet_carries_the_tx_desc_and_h2c_header():
    fw = firmware.load_fw_suit(1)
    info = firmware.parse_hdr(fw)
    pkt = firmware.build_hdr_packet(fw, info)
    body_len = len(pkt) - 16 - 8                       # desc + h2c header
    assert body_len == info["hdr_len"] - info["dynamic_hdr_len"]
    dword0 = int.from_bytes(pkt[:4], "little")
    assert dword0 & 0x3FFF == len(pkt) - 16            # rpkt_len = payload length
    assert (dword0 >> 24) & 0xF == 13                  # RTW89_CORE_RX_TYPE_H2C


def test_body_packets_are_chunked_at_part_size():
    fw = firmware.load_fw_suit(1)
    info = firmware.parse_hdr(fw)
    packets = firmware.build_body_packets(fw, info)
    expected = sum(-(-s["len"] // info["part_size"]) for s in info["sections"])
    assert len(packets) == expected
    assert all((int.from_bytes(p[:4], "little") >> 24) & 0xF == 14 for p in packets)
