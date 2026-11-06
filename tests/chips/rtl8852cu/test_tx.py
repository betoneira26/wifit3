"""M5 TX: AX v1 mgmt descriptor packing and the driver bulk-OUT injection path."""
import struct

from wifit3.chips.rtl8852cu import tx
from wifit3.chips.rtl8852cu.driver import RTL8852CUDriver


def _mgmt_frame(addr1: bytes = b"\xff" * 6, seq: int = 0) -> bytes:
    frame = bytearray(24)
    frame[0] = 0x80
    frame[4:10] = addr1
    frame[22:24] = ((seq & 0xFFF) << 4).to_bytes(2, "little")
    return bytes(frame)


def test_desc_is_body_plus_info():
    desc = tx.build_tx_desc_mgmt(_mgmt_frame())
    assert len(desc) == tx.TXWD_BODY_SIZE + tx.TXWD_INFO_SIZE == 56


def test_body0_sets_wdinfo_chdma_stf_and_page():
    d0 = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame()))[0]
    assert d0 & (1 << 22)
    assert (d0 >> 16) & 0xF == tx.TXCH_CH8
    assert d0 & (1 << 10)
    assert d0 & (1 << 7)


def test_body2_carries_qsel_size_and_macid():
    frame = _mgmt_frame()
    d2 = struct.unpack_from("<I", tx.build_tx_desc_mgmt(frame), 8)[0]
    assert (d2 >> 17) & 0x3F == tx.QSEL_B0_MGMT
    assert d2 & 0x3FFF == len(frame)
    assert (d2 >> 24) & 0x7F == 0


def test_body3_mirrors_seq_ctrl():
    d3 = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame(seq=0x123)), 12)[0]
    assert d3 & 0xFFF == 0x123


def test_body7_selects_band_rate():
    w2g = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame()), 28)[0]
    w5g = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame(), band_is_2g=False), 28)[0]
    assert w2g & (1 << 31) and (w2g >> 16) & 0x1FF == tx.HW_RATE_CCK1
    assert w5g & (1 << 31) and (w5g >> 16) & 0x1FF == tx.HW_RATE_OFDM6


def test_info0_disables_data_feedback():
    info0 = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame()), 32)[0]
    assert info0 & (1 << 10)


def test_info4_requests_rts_for_unicast_only():
    unicast = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame(b"\x02" * 6)), 48)[0]
    broadcast = struct.unpack_from("<I", tx.build_tx_desc_mgmt(_mgmt_frame()), 48)[0]
    assert unicast & (1 << 31) and unicast & (1 << 27)
    assert broadcast & (1 << 31) and not broadcast & (1 << 27)


async def test_inject_frame_bulk_outs_desc_then_stamped_mpdu(mocker):
    driver = RTL8852CUDriver()
    driver._mgmt_ep = 0x05
    driver.transport = mocker.Mock()
    driver._band_is_2g = True
    frame = _mgmt_frame()

    assert await driver.inject_frame(frame) is True

    endpoint, payload = driver.transport.bulk_out.call_args[0]
    assert endpoint == 0x05
    assert len(payload) == 56 + len(frame)
    assert payload[56:58] == frame[:2]
    assert struct.unpack_from("<H", payload, 56 + 22)[0] == 1 << 4


async def test_inject_frame_without_endpoint_returns_false(mocker):
    driver = RTL8852CUDriver()
    driver.transport = mocker.Mock()
    assert await driver.inject_frame(_mgmt_frame()) is False
    driver.transport.bulk_out.assert_not_called()


def test_driver_fake_mac_is_spoofable():
    from wifit3.chips.driver import FakeMacSupport
    assert RTL8852CUDriver.FAKE_MAC == FakeMacSupport.SPOOFABLE


async def test_enter_and_exit_active_monitor(mocker):
    from wifit3.chips.rtl8852cu import firmware

    driver = RTL8852CUDriver()
    driver._h2c_ep = 0x02
    driver.transport = mocker.Mock()
    driver.transport.h2c_seq = 0

    spy_addr_cam = mocker.spy(firmware, "h2c_addr_cam")
    spy_cam = mocker.spy(firmware, "h2c_cam")

    target_mac = b"\x02\x11\x22\x33\x44\x55"
    ret = await driver.enter_active_monitor(target_mac)
    assert ret == target_mac
    assert driver._active_mac == target_mac
    assert spy_addr_cam.call_count == 1
    assert spy_addr_cam.call_args.kwargs["sma"] == target_mac

    await driver.exit_active_monitor()
    assert driver._active_mac is None
    assert spy_cam.call_count == 1
