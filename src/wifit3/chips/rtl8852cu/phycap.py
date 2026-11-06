"""RTL8852CU phycap (M3): the trimmed calibration values that RF setup and RFK consume.

The phycap area is a second slice of the same physical efuse (0x590, 0x60 bytes on the 8852C).
Each value's efuse address maps to a fixed offset in that slice; 0xff means "not programmed", and
the kernel then falls back to defaults. [SRC] rtw8852c.c:678-830, rtw8852c.c:3244.
"""
from . import efuse

PHYCAP_ADDR = 0x590
PHYCAP_SIZE = 0x60
RF_PATH_NUM = 2
TSSI_TRIM_CH_GROUP_NUM = 8
TSSI_TRIM_CH_GROUP_NUM_6G = 16

_TSSI_TRIM_ADDR = (0x5D6, 0x5AB)
_TSSI_TRIM_ADDR_6G = (0x5CE, 0x5A3)
_THM_TRIM_ADDR = (0x5DF, 0x5DC)
_PABIAS_TRIM_ADDR = (0x5DE, 0x5DB)


def dump(t) -> bytes:
    """rtw89_parse_phycap_map_ax's dump half. [SRC] efuse.c:350-380."""
    return efuse.dump_physical(t, PHYCAP_ADDR, PHYCAP_SIZE)


def parse(m: bytes) -> dict:
    """rtw8852c_read_phycap: per-path TSSI trim (2.4/5 and 6 GHz), thermal trim and PA bias trim.
    Addresses are stored highest-first, so offset = addr - phycap_addr - j. [SRC]
    rtw8852c.c:678-830."""
    tssi = [[0] * TSSI_TRIM_CH_GROUP_NUM for _ in range(RF_PATH_NUM)]
    tssi_6g = [[0] * TSSI_TRIM_CH_GROUP_NUM_6G for _ in range(RF_PATH_NUM)]
    programmed = False
    for path in range(RF_PATH_NUM):
        for j in range(TSSI_TRIM_CH_GROUP_NUM):
            val = m[_TSSI_TRIM_ADDR[path] - PHYCAP_ADDR - j]
            tssi[path][j] = val
            programmed |= val != 0xFF
        for j in range(TSSI_TRIM_CH_GROUP_NUM_6G):
            val = m[_TSSI_TRIM_ADDR_6G[path] - PHYCAP_ADDR - j]
            tssi_6g[path][j] = val
            programmed |= val != 0xFF

    if not programmed:
        tssi = [[0] * TSSI_TRIM_CH_GROUP_NUM for _ in range(RF_PATH_NUM)]
        tssi_6g = [[0] * TSSI_TRIM_CH_GROUP_NUM_6G for _ in range(RF_PATH_NUM)]

    thermal = [m[_THM_TRIM_ADDR[p] - PHYCAP_ADDR] for p in range(RF_PATH_NUM)]
    pa_bias = [m[_PABIAS_TRIM_ADDR[p] - PHYCAP_ADDR] for p in range(RF_PATH_NUM)]
    return {
        "tssi_trim": tssi,
        "tssi_trim_6g": tssi_6g,
        "thermal_trim": thermal,
        "pa_bias_trim": pa_bias,
        "pg_thermal_trim": any(v != 0xFF for v in thermal),
        "pg_pa_bias_trim": any(v != 0xFF for v in pa_bias),
    }
