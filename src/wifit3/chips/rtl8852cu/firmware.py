"""RTL8852CU firmware download, ported from the mainline rtw89 tree (fw.c, mac.c, core.c, usb.c).

The firmware file is a multi-firmware (mfw) container: the NORMAL sub-firmware for this chip cut
is extracted, its v1 header parsed, and header + code sections are pushed to the WLAN CPU as
fwdl/H2C packets on the H2C bulk-OUT endpoint. Each packet carries a 16-byte fwcmd descriptor
(struct rtw89_rxdesc_short) and, for the header, an 8-byte H2C command header in front of the
firmware bytes. See RTL8852CU.md.
"""
import struct
import time
from pathlib import Path
from typing import Optional

from .constants import (
    FW_ASSET, RTW89_MFW_SIG, RTW89_FW_NORMAL,
    H2C_DESC_SIZE, H2C_HEADER_LEN, RTW89_USB_MOD512_PADDING,
    AX_RXD_RPKT_LEN_MASK, AX_RXD_RPKT_TYPE_SHIFT,
    RTW89_CORE_RX_TYPE_H2C, RTW89_CORE_RX_TYPE_FWDL,
    H2C_HDR_CAT_MAC, H2C_CL_MAC_FWDL, H2C_FUNC_MAC_FWHDR_DL,
    H2C_HDR_CLASS_SHIFT, H2C_HDR_TOTAL_LEN_MASK,
    FW_HDR_V1_W6_SEC_NUM_SHIFT, FW_HDR_V1_W6_SEC_NUM_MASK,
    FW_HDR_V1_W7_DYN_HDR, FW_HDR_V1_W7_PART_SIZE_MASK,
    FW_HDR_W1_MAJOR_MASK, FW_HDR_W1_MINOR_SHIFT, FW_HDR_W1_SUBVERSION_SHIFT,
    FW_HDR_W1_SUBINDEX_SHIFT, FW_HDR_W3_LEN_SHIFT, FW_HDR_W3_LEN_MASK,
    FWSECTION_HDR_V1_W1_SEC_SIZE_MASK, FWSECTION_HDR_V1_W1_SECTIONTYPE_SHIFT,
    FWSECTION_HDR_V1_W1_CHECKSUM, FWDL_SECTION_PER_PKT_LEN,
    FWDL_SECURITY_SECTION_TYPE, FWDL_SECTION_CHKSUM_LEN, FWDL_SECURITY_SIGLEN,
    FWDL_MSS_POOL_DEFKEYSETS_SIZE, FORMATTED_MSSC,
    MSS_POOL_HDR_LEN, MSS_SIGNATURE,
    R_AX_HALT_H2C_CTRL, R_AX_HALT_C2H_CTRL,
    R_AX_WCPU_FW_CTRL, B_AX_H2C_PATH_RDY, B_AX_FWDL_PATH_RDY, B_AX_WCPU_FWDL_STS_MASK,
    FWDL_WAIT_CNT, FWDL_WAIT_CNT_USB, RTW89_FWDL_WCPU_FW_INIT_RDY,
    R_AX_H2CREG_DATA0_V1, R_AX_H2CREG_DATA1_V1, R_AX_H2CREG_DATA2_V1, R_AX_H2CREG_DATA3_V1,
    R_AX_C2HREG_DATA0_V1, R_AX_C2HREG_DATA1_V1, R_AX_C2HREG_DATA2_V1, R_AX_C2HREG_DATA3_V1,
    R_AX_H2CREG_CTRL_V1, R_AX_C2HREG_CTRL_V1, B_AX_H2CREG_TRIGGER, R_AX_UDM1,
    B_AX_UDM1_HALMAC_H2C_DEQ_CNT, B_AX_UDM1_HALMAC_C2H_ENQ_CNT,
    RTW89_H2CREG_HDR_FUNC_MASK, RTW89_H2CREG_HDR_LEN_MASK,
    RTW89_C2HREG_HDR_FUNC_MASK, RTW89_C2HREG_HDR_LEN_MASK,
    RTW89_H2CREG_MAX, RTW89_H2CREG_HDR_LEN, RTW89_C2HREG_HDR_LEN,
    C2H_TIMEOUT_USB_POLL_US, H2C_REG_IDLE_WAIT_US,
    RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE,
)

_ASSET_PATH = Path(__file__).resolve().parent / "assets" / FW_ASSET


def _gb(word: int, shift: int, mask: int) -> int:
    return (word >> shift) & mask


def load_fw_suit(cv: int) -> bytes:
    """rtw89_mfw_recognize: from the multi-firmware file, return the NORMAL sub-firmware whose
    cut is the closest at or below hal.cv (non-MP). [SRC] fw.c:562-666."""
    data = _ASSET_PATH.read_bytes()
    if data[0] != RTW89_MFW_SIG:
        return data                                   # legacy flat firmware
    best = None                                       # (cv, shift, size)
    for i in range(data[1]):
        off = 16 + i * 16                             # mfw_hdr is 16 bytes, mfw_info is 16 bytes
        cut, typ, mp = data[off], data[off + 1], data[off + 2]
        shift, size = struct.unpack_from("<II", data, off + 4)
        if typ == RTW89_FW_NORMAL and cut <= cv and not mp and (best is None or best[0] < cut):
            best = (cut, shift, size)
    if best is None:
        raise RuntimeError("rtl8852cu: no suitable NORMAL firmware in the mfw file")
    return data[best[1]:best[1] + best[2]]


def parse_hdr(fw: bytes) -> dict:
    """rtw89_fw_hdr_parser_v0 (the 8852C firmware ships v0 headers: RTW89_FW_HDR_VER_CODE != 1).
    AX forces part_size to FWDL_SECTION_PER_PKT_LEN. Returns {section_num, part_size, hdr_len,
    dynamic_hdr_len, sections}, each section {addr, len, type, ignore}. Secure boot is off on this
    card, so no key is selected and nothing is copied. [SRC] fw.c:140-270."""
    w = struct.unpack_from("<8I", fw, 0)
    ver = (((w[1] >> FW_HDR_W1_MINOR_SHIFT) & 0xFF)
           | (((w[1] >> FW_HDR_W1_SUBVERSION_SHIFT) & 0xFF) << 8)
           | (((w[1] >> FW_HDR_W1_SUBINDEX_SHIFT) & 0xFF) << 16)
           | ((w[1] & FW_HDR_W1_MAJOR_MASK) << 24))
    if ver == 1:
        raise RuntimeError("rtl8852cu: v1 firmware header, parser is v0-only")
    section_num = (w[6] >> FW_HDR_V1_W6_SEC_NUM_SHIFT) & 0xFF
    base_hdr_len = 32 + section_num * 16              # struct_size(fw_hdr, sections, n)
    if w[7] & FW_HDR_V1_W7_DYN_HDR:
        hdr_len = (w[3] >> FW_HDR_W3_LEN_SHIFT) & FW_HDR_W3_LEN_MASK
        dynamic_hdr_len = hdr_len - base_hdr_len
        if dynamic_hdr_len and struct.unpack_from("<I", fw, base_hdr_len)[0] != dynamic_hdr_len:
            raise RuntimeError("rtl8852cu: invalid firmware dynamic header length")
    else:
        hdr_len = base_hdr_len
        dynamic_hdr_len = 0

    sections = []
    binp = hdr_len
    for i in range(section_num):
        s = struct.unpack_from("<4I", fw, 32 + i * 16)
        sec_type = _gb(s[1], FWSECTION_HDR_V1_W1_SECTIONTYPE_SHIFT, 0xF)
        length = s[1] & FWSECTION_HDR_V1_W1_SEC_SIZE_MASK
        if s[1] & FWSECTION_HDR_V1_W1_CHECKSUM:
            length += FWDL_SECTION_CHKSUM_LEN
        mssc_len = 0
        if sec_type == FWDL_SECURITY_SECTION_TYPE:
            sections.append({"addr": binp, "len": length, "type": sec_type,
                             "ignore": False, "_mssc": s[2]})
            sections[-1]["_bin"] = binp
        else:
            sections.append({"addr": binp, "len": length, "type": sec_type, "ignore": False})
        binp += length + mssc_len

    for idx, sec in enumerate(sections):
        mssc = sec.pop("_mssc", None)
        if mssc is None:
            continue
        content = sec["addr"]
        if (mssc & 0xFF) == FORMATTED_MSSC:
            mssc_len = _mssc_pool_size(fw, content, sec["len"])
        else:
            mssc_len = mssc * FWDL_SECURITY_SIGLEN
        if mssc_len:
            # The MSS key pool trails the security section: only the *later* sections shift.
            for later in sections[idx + 1:]:
                later["addr"] += mssc_len
            binp += mssc_len

    if binp != len(fw):
        raise RuntimeError(f"rtl8852cu: firmware size mismatch (bin {binp} != fw {len(fw)})")
    return {"section_num": section_num, "part_size": FWDL_SECTION_PER_PKT_LEN, "hdr_len": hdr_len,
            "dynamic_hdr_len": dynamic_hdr_len, "version": ver, "sections": sections}


def _mssc_pool_size(fw: bytes, content: int, length: int) -> int:
    """__parse_formatted_mssc with secure boot off: size the MSS key pool trailing the section, no
    key selection. [SRC] fw.c:282-362."""
    mh = content + length
    if fw[mh:mh + len(MSS_SIGNATURE)] != MSS_SIGNATURE:
        raise RuntimeError("rtl8852cu: wrong MSS signature")
    defen = fw[mh + 16]
    mssdev_max = fw[mh + 21]
    keypair_num = struct.unpack_from("<H", fw, mh + 22)[0]
    msscust_max = struct.unpack_from("<H", fw, mh + 24)[0]
    msskey_num_max = struct.unpack_from("<H", fw, mh + 26)[0]
    rmp_tbl_size = (msskey_num_max * msscust_max * mssdev_max) >> 3
    if defen:
        rmp_tbl_size += FWDL_MSS_POOL_DEFKEYSETS_SIZE
    key_sign_len = struct.unpack_from("<H", fw, content + 60)[0] >> 2
    if not key_sign_len:
        key_sign_len = 512
    return MSS_POOL_HDR_LEN + rmp_tbl_size + keypair_num * key_sign_len


def _txd(pkt_size: int, fwdl: bool) -> bytes:
    """rtw89_build_txwd_fwcmd0_v1 + the zeroed rxdesc_short body. [SRC] core.c:1896-1917."""
    rx_type = RTW89_CORE_RX_TYPE_FWDL if fwdl else RTW89_CORE_RX_TYPE_H2C
    dword0 = (pkt_size & AX_RXD_RPKT_LEN_MASK) | (rx_type << AX_RXD_RPKT_TYPE_SHIFT)
    return struct.pack("<I", dword0) + b"\x00" * (H2C_DESC_SIZE - 4)


def _h2c_fwdl_hdr(payload_len: int) -> bytes:
    """rtw89_h2c_pkt_set_hdr_fwdl: 8-byte FWDL command header, h2c_seq 0. [SRC] fw.c:1677."""
    hdr0 = H2C_HDR_CAT_MAC | (H2C_CL_MAC_FWDL << H2C_HDR_CLASS_SHIFT) | H2C_FUNC_MAC_FWHDR_DL
    hdr1 = (payload_len + H2C_HEADER_LEN) & H2C_HDR_TOTAL_LEN_MASK
    return struct.pack("<II", hdr0, hdr1)


def _pad_mod512(payload: bytes) -> bytes:
    """rtw89_usb_tx_write_fwcmd: never emit a whole-packet size that is a multiple of 512.
    [SRC] usb.c:370-391."""
    if (len(payload) + H2C_DESC_SIZE) % 512 == 0:
        return payload + b"\x00" * RTW89_USB_MOD512_PADDING
    return payload


def build_hdr_packet(fw: bytes, info: dict) -> bytes:
    """__rtw89_fw_download_hdr + __rtw89_fw_download_tweak_hdr_v1: the header packet is the first
    (hdr_len - dynamic_hdr_len) bytes of the firmware, with part_size written to w7, ignored
    sections compacted out, the w6 section count updated, and the freed headers trimmed.
    [SRC] fw.c:1692-1805."""
    length = info["hdr_len"] - info["dynamic_hdr_len"]
    hdr = bytearray(fw[:length])
    w7 = struct.unpack_from("<I", hdr, 28)[0]
    struct.pack_into("<I", hdr, 28, (w7 & ~FW_HDR_V1_W7_PART_SIZE_MASK) | info["part_size"])
    dst = 0
    for i, sec in enumerate(info["sections"]):
        if sec["ignore"]:
            continue
        if dst != i:
            hdr[48 + dst * 16:48 + dst * 16 + 16] = hdr[48 + i * 16:48 + i * 16 + 16]
        dst += 1
    w6 = struct.unpack_from("<I", hdr, 24)[0]
    struct.pack_into("<I", hdr, 24, (w6 & ~FW_HDR_V1_W6_SEC_NUM_MASK)
                     | (dst << FW_HDR_V1_W6_SEC_NUM_SHIFT))
    hdr = bytes(hdr[:length - (info["section_num"] - dst) * 16])
    payload = _pad_mod512(_h2c_fwdl_hdr(len(hdr)) + hdr)
    return _txd(len(payload), False) + payload


def build_body_packets(fw: bytes, info: dict) -> list:
    """__rtw89_fw_download_main: send each non-ignored section in part_size chunks, each behind a
    fwdl descriptor. [SRC] fw.c:1810-1870."""
    part_size = info["part_size"]
    packets = []
    for sec in info["sections"]:
        if sec["ignore"]:
            continue
        section = fw[sec["addr"]:sec["addr"] + sec["len"]]
        pos = 0
        residue = sec["len"]
        while residue:
            chunk = section[pos:pos + min(residue, part_size)]
            if not chunk:
                raise RuntimeError("rtl8852cu: firmware section length overruns the suite")
            payload = _pad_mod512(chunk)
            packets.append(_txd(len(payload), True) + payload)
            pos += len(chunk)
            residue -= len(chunk)
    return packets


def _poll8(t, addr: int, cond, timeout_us: int) -> int:
    """read_poll_timeout_atomic(rtw89_read8, ...). The kernel's budget is wall-clock (1us poll
    interval); a Python USB read costs ~1ms, so poll against a monotonic deadline.
    Give at least 2.0 seconds on USB so the bootloader has time to parse packets."""
    deadline = time.monotonic() + max(timeout_us / 1_000_000, 2.0)
    val = 0
    while True:
        val = t.read8(addr)
        if cond(val):
            return val
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"rtl8852cu: firmware poll timeout on 0x{addr:04x} (last 0x{val:02x})")


def check_path_ready(t, h2c_or_fwdl: bool) -> None:
    """rtw89_fwdl_check_path_ready_ax. USB budget is FWDL_WAIT_CNT_USB. [SRC] mac.c:7428-7440."""
    check = B_AX_H2C_PATH_RDY if h2c_or_fwdl else B_AX_FWDL_PATH_RDY
    _poll8(t, R_AX_WCPU_FW_CTRL, lambda v: v & check, FWDL_WAIT_CNT_USB)


def probe_alive(t) -> bool:
    """Whether a firmware is running and servicing the register mailbox. No register tells that
    apart from a cold ROM (both read INIT_RDY), so the only honest probe is a real query: a chip
    with no firmware never answers, which is the download path rather than a failure."""
    try:
        msg_reg(t, RTW89_FWCMD_H2CREG_FUNC_GET_FEATURE, words=[0], content_len=0)
        return True
    except TimeoutError:
        reset_mailbox(t)
        return False


def reset_mailbox(t) -> None:
    """Drop the H2C trigger and C2H acknowledge a previous session may have left pending, so the
    next register-mailbox query does not wait on a request no firmware will consume."""
    t.write8(R_AX_H2CREG_CTRL_V1, 0)
    t.write8(R_AX_C2HREG_CTRL_V1, 0)
    t.h2c_counter = 0
    t.c2h_counter = 0


def check_rdy(t) -> None:
    """rtw89_fw_check_rdy(RTW89_FWDL_CHECK_FREERTOS_DONE), AX: the status field must read
    WCPU_FW_INIT_RDY. [SRC] fw.c:106-138, mac.c:106 (rtw89_fw_get_rdy_ax)."""
    shift = (B_AX_WCPU_FWDL_STS_MASK & -B_AX_WCPU_FWDL_STS_MASK).bit_length() - 1
    _poll8(t, R_AX_WCPU_FW_CTRL,
           lambda v: (v & B_AX_WCPU_FWDL_STS_MASK) >> shift == RTW89_FWDL_WCPU_FW_INIT_RDY,
           FWDL_WAIT_CNT)


def download_suit(t, h2c_ep: int, fw: bytes, info: dict) -> None:
    """rtw89_fw_download_suit: H2C path-ready, header packet, fwdl path-ready, halt-ctrl clear,
    then the section packets. AX checks fw-ready only once per download, after all suites.
    [SRC] fw.c:1977-2010."""
    check_path_ready(t, True)
    t.bulk_out(h2c_ep, build_hdr_packet(fw, info))
    check_path_ready(t, False)
    t.write32(R_AX_HALT_H2C_CTRL, 0)
    t.write32(R_AX_HALT_C2H_CTRL, 0)
    for pkt in build_body_packets(fw, info):
        t.bulk_out(h2c_ep, pkt)


def download(t, h2c_ep: int, cv: int) -> None:
    """rtw89_fw_download(NORMAL) tail: transfer the suit, reset the mailbox counters, and wait for
    FreeRTOS-ready. The CPU disable/enable around it lives in mac.enable_cpu_fwdl / disable_cpu.
    [SRC] fw.c:2010-2075."""
    fw = load_fw_suit(cv)
    download_suit(t, h2c_ep, fw, parse_hdr(fw))
    t.h2c_seq = 0
    t.h2c_counter = 0
    t.c2h_counter = 0
    time.sleep(0.005)                                 # mdelay(5)
    check_rdy(t)


_H2C_DATA_REGS = (R_AX_H2CREG_DATA0_V1, R_AX_H2CREG_DATA1_V1,
                  R_AX_H2CREG_DATA2_V1, R_AX_H2CREG_DATA3_V1)
_C2H_DATA_REGS = (R_AX_C2HREG_DATA0_V1, R_AX_C2HREG_DATA1_V1,
                  R_AX_C2HREG_DATA2_V1, R_AX_C2HREG_DATA3_V1)


def write_h2c_reg(t, func: int, words=(), content_len: int = 0) -> None:
    """rtw89_fw_write_h2c_reg: wait for the mailbox to go idle, pack the H2C header into word 0,
    write the four data registers, bump the dequeue counter, then trigger the firmware.
    [SRC] fw.c:9219-9249."""
    _poll8(t, R_AX_H2CREG_CTRL_V1, lambda v: v == 0, H2C_REG_IDLE_WAIT_US)
    regs = list(words)[:RTW89_H2CREG_MAX]
    regs += [0] * (RTW89_H2CREG_MAX - len(regs))
    n_words = -(-(content_len + RTW89_H2CREG_HDR_LEN) // 4)
    regs[0] &= ~(RTW89_H2CREG_HDR_FUNC_MASK | RTW89_H2CREG_HDR_LEN_MASK)
    regs[0] |= func & RTW89_H2CREG_HDR_FUNC_MASK
    regs[0] |= (n_words << 8) & RTW89_H2CREG_HDR_LEN_MASK
    for addr, word in zip(_H2C_DATA_REGS, regs):
        t.write32(addr, word & 0xFFFFFFFF)
    t.h2c_counter = (t.h2c_counter + 1) & 0xFF
    t.write8_mask(R_AX_UDM1 + 1, B_AX_UDM1_HALMAC_H2C_DEQ_CNT, t.h2c_counter)
    t.write8(R_AX_H2CREG_CTRL_V1, B_AX_H2CREG_TRIGGER)


def _consume_c2h_reg(t) -> list:
    """Read and acknowledge the four C2H data words. [SRC] fw.c:9273-9293."""
    words = [t.read32(addr) for addr in _C2H_DATA_REGS]
    t.write8(R_AX_C2HREG_CTRL_V1, 0)
    t.c2h_counter = (t.c2h_counter + 1) & 0xFF
    t.write8_mask(R_AX_UDM1 + 1, B_AX_UDM1_HALMAC_C2H_ENQ_CNT, t.c2h_counter)
    return words


def read_c2h_reg(t, timeout_us: int = C2H_TIMEOUT_USB_POLL_US) -> dict:
    """rtw89_fw_read_c2h_reg: poll the C2H control register, read the four data words, clear the
    control register, and decode the header. Returns {id, content_len, words}. [SRC]
    fw.c:9252-9295."""
    _poll8(t, R_AX_C2HREG_CTRL_V1, lambda v: v != 0, timeout_us)
    words = _consume_c2h_reg(t)
    c2h_id = words[0] & RTW89_C2HREG_HDR_FUNC_MASK
    content_len = (((words[0] & RTW89_C2HREG_HDR_LEN_MASK) >> 8) << 2) - RTW89_C2HREG_HDR_LEN
    return {"id": c2h_id, "content_len": content_len, "words": words}


def msg_reg(t, func: int, words=(), content_len: int = 0,
            timeout_us: int = C2H_TIMEOUT_USB_POLL_US) -> dict:
    """rtw89_fw_msg_reg with both an H2C and a C2H side. A reply left pending by an earlier
    timed-out request is drained first so it cannot be mistaken for this request's answer.
    [SRC] fw.c:9297-9325."""
    if t.read8(R_AX_C2HREG_CTRL_V1) != 0:
        _consume_c2h_reg(t)
    write_h2c_reg(t, func, words, content_len)
    return read_c2h_reg(t, timeout_us)


H2C_HDR_CAT_MASK = 0x00000003
H2C_HDR_CLASS_MASK = 0x000000FC
H2C_HDR_FUNC_MASK = 0x0000FF00
H2C_HDR_H2C_SEQ_MASK = 0xFF000000
H2C_HDR_REC_ACK = 1 << 14
H2C_HDR_DONE_ACK = 1 << 15


def _pb(mask: int, val: int) -> int:
    shift = (mask & -mask).bit_length() - 1
    return (val << shift) & mask


def h2c_command(t, h2c_ep: int, cat: int, cls: int, func: int, payload: bytes,
                rack: bool = False, dack: bool = True) -> None:
    """Send an H2C command over the bulk-OUT endpoint. [SRC] fw.c:1624-1647, core.c:1892-1900."""
    total = len(payload) + H2C_HEADER_LEN
    seq = getattr(t, "h2c_seq", 0)
    hdr0 = (_pb(H2C_HDR_CAT_MASK, cat)
            | _pb(H2C_HDR_CLASS_MASK, cls)
            | _pb(H2C_HDR_FUNC_MASK, func)
            | _pb(H2C_HDR_H2C_SEQ_MASK, seq))
    hdr1 = (_pb(H2C_HDR_TOTAL_LEN_MASK, total)
            | (H2C_HDR_REC_ACK if rack else 0)
            | (H2C_HDR_DONE_ACK if dack else 0))
    t.h2c_seq = (seq + 1) & 0xFF
    fwcmd = struct.pack("<II", hdr0, hdr1) + payload
    pkt = _pad_mod512(fwcmd)
    t.bulk_out(h2c_ep, _txd(len(pkt), False) + pkt)


def h2c_macid_pause(t, h2c_ep: int, sh: int, grp: int, pause: bool) -> None:
    """rtw89_fw_h2c_macid_pause for 8852C (H2C_FUNC_MAC_MACID_PAUSE = 0x8). [SRC] fw.c:5218."""
    payload = bytearray(32)
    setbit = 1 << sh
    struct.pack_into("<I", payload, 16 + grp * 4, setbit)
    if pause:
        struct.pack_into("<I", payload, 0 + grp * 4, setbit)
    h2c_command(t, h2c_ep, 1, 9, 8, bytes(payload), rack=True, dack=False)


def h2c_role_maintain(t, h2c_ep: int, macid: int, wifi_role: int = 7) -> None:
    """rtw89_fw_h2c_role_maintain(ROLE_CREATE): w0. [SRC] fw.c:4983."""
    w0 = (macid & 0xFF) | ((wifi_role & 0xF) << 13)
    h2c_command(t, h2c_ep, 1, 8, 4, struct.pack("<I", w0), rack=False, dack=True)


def h2c_join_info(t, h2c_ep: int, macid: int, wifi_role: int = 7, dis_conn: bool = True) -> None:
    """rtw89_fw_h2c_join_info (AX v0): w0 only (4 bytes). [SRC] fw.c:5079."""
    w0 = (macid & 0xFF) | ((1 if dis_conn else 0) << 8) | ((wifi_role & 0xF) << 26)
    h2c_command(t, h2c_ep, 1, 8, 0, struct.pack("<I", w0), rack=False, dack=True)


def _addr_hash(addr: bytes) -> int:
    h = 0
    for b in addr:
        h ^= b
    return h


def h2c_addr_cam(t, h2c_ep: int, *, sma: bytes, tma: bytes, net_type: int,
                 bssid: bytes, bssid_mask: int) -> None:
    """rtw89_fw_h2c_cam(addrcam_ver 0): 15 u32 words. [SRC] fw.c:2310."""
    w = [0] * 15
    w[1] = 16 << 16
    w[2] = 1 | (net_type << 1) | (_addr_hash(sma) << 16) | (_addr_hash(tma) << 24)
    w[4] = int.from_bytes(sma[0:4], "little")
    w[5] = int.from_bytes(sma[4:6], "little") | (int.from_bytes(tma[0:2], "little") << 16)
    w[6] = int.from_bytes(tma[2:6], "little")
    w[9] = 0
    w[12] = 8 << 16
    w[13] = 1 | (bssid_mask << 1) | (bssid[0] << 16) | (bssid[1] << 24)
    w[14] = int.from_bytes(bssid[2:6], "little")
    h2c_command(t, h2c_ep, 1, 6, 0, struct.pack("<15I", *w), rack=False, dack=True)


def h2c_cam(t, h2c_ep: int, mac: Optional[bytes] = None) -> None:
    """rtw89_fw_h2c_cam for monitor mode."""
    z = b"\x00" * 6
    sma = mac if mac and len(mac) == 6 else z
    h2c_addr_cam(t, h2c_ep, sma=sma, tma=z, net_type=0, bssid=z, bssid_mask=0x3F)


def h2c_default_cmac_tbl(t, h2c_ep: int, macid: int = 0) -> None:
    """rtw89_fw_h2c_default_cmac_tbl (CCTLINFO_UD_V1 = 0xA): 17 u32 words. [SRC] fw.c:3637."""
    words = [0] * 17
    words[0] = (macid & 0x7F) | 0x80
    words[1] = 1 << 21
    words[9] = 1 << 21
    h2c_command(t, h2c_ep, 1, 5, 0xA, struct.pack("<17I", *words), rack=False, dack=True)


def h2c_fw_log(t, h2c_ep: int, enable: bool = False) -> None:
    """rtw89_fw_h2c_fw_log. [SRC] fw.c:2848."""
    comp = 0x3F if enable else 0
    payload = struct.pack("<II", 0x01000004, comp)
    h2c_command(t, h2c_ep, 1, 2, 0, payload, rack=False, dack=False)

