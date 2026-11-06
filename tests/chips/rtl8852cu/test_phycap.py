"""RTL8852CU phycap parsing (offsets are relative to the 0x590 phycap slice)."""
from wifit3.chips.rtl8852cu import phycap


def _map(**fields) -> bytes:
    m = bytearray(b"\xff" * phycap.PHYCAP_SIZE)
    for addr, val in fields.items():
        m[int(addr, 16) - phycap.PHYCAP_ADDR] = val
    return bytes(m)


def test_thermal_and_pa_bias_trim_are_read_per_path():
    m = _map(**{"0x5df": 0x21, "0x5dc": 0x27, "0x5de": 0x2F, "0x5db": 0x30})
    parsed = phycap.parse(m)
    assert parsed["thermal_trim"] == [0x21, 0x27]
    assert parsed["pa_bias_trim"] == [0x2F, 0x30]
    assert parsed["pg_thermal_trim"] and parsed["pg_pa_bias_trim"]


def test_unprogrammed_tssi_falls_back_to_zero():
    parsed = phycap.parse(_map())
    assert parsed["tssi_trim"] == [[0] * 8, [0] * 8]
    assert parsed["tssi_trim_6g"] == [[0] * 16, [0] * 16]
    assert not parsed["pg_thermal_trim"]
    assert not parsed["pg_pa_bias_trim"]


def test_programmed_tssi_is_kept():
    m = _map(**{"0x5d6": 0x11, "0x5ce": 0x22})
    parsed = phycap.parse(m)
    assert parsed["tssi_trim"][0][0] == 0x11
    assert parsed["tssi_trim_6g"][0][0] == 0x22
    assert parsed["tssi_trim"][1][0] == 0xFF      # path B untouched stays 0xff (not "no PG")
