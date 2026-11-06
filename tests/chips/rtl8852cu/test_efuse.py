"""RTL8852CU efuse: logical-map assembly and the parsed fields."""
from wifit3.chips.rtl8852cu import efuse


def _word(hdr1: int, hdr2: int, words: list) -> bytes:
    """One physical efuse block: header then the enabled words (word_en bit set == disabled)."""
    out = bytearray([hdr1, hdr2])
    for w in words:
        out += bytes(w)
    return bytes(out)


def _pad(block: bytes) -> bytes:
    """Place one block right after the 4-byte security-ctrl area, 0xff-padded to chip size."""
    head = b"\xff\xff\xff\xff" + block
    return head + b"\xff" * (efuse.PHYSICAL_EFUSE_SIZE - len(head))


def test_logical_map_places_words_by_block_index():
    # sec_ctrl (4 bytes) then one block: blk 1, only word 2 enabled, data 0x1234.
    phy = _pad(_word(0x00, 0x1B, [(0x12, 0x34)]))
    log = efuse.logical_map(phy)
    assert log[(1 << 3) + (2 << 1):(1 << 3) + (2 << 1) + 2] == b"\x12\x34"
    assert log[0] == 0xFF


def test_logical_map_stops_at_padding():
    phy = _pad(_word(0x00, 0x00, [(0xaa, 0xbb)]))
    log = efuse.logical_map(phy)
    assert log[0:2] == b"\xaa\xbb"
    assert log[2] == 0xFF


def test_parse_reads_the_tail_union_fields():
    log = bytearray(b"\xff" * efuse.LOGICAL_EFUSE_SIZE)
    log[efuse.OFF_RFE_TYPE] = 1
    log[efuse.OFF_MAC_USB:efuse.OFF_MAC_USB + 6] = bytes.fromhex("90de80ec8d42")
    log[efuse.OFF_CHANNEL_PLAN] = 0x7F
    log[efuse.OFF_XTAL_K] = 0x41
    parsed = efuse.parse(bytes(log))
    assert parsed["mac_addr_str"] == "90:de:80:ec:8d:42"
    assert parsed["rfe_type"] == 1
    assert parsed["channel_plan"] == 0x7F
    assert parsed["xtal_k"] == 0x41
