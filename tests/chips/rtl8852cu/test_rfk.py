"""Unit tests for the RTL8852CU RF calibrations: rck, lck, rx_dck."""
from unittest.mock import MagicMock

from wifit3.chips.rtl8852cu import rfk


class RFRecorder:
    """Records write_rf calls; serves read_rf from a per-register reader.

    ``reader(path, addr, mask)`` returns the raw register value; it is masked and shifted the same
    way phy.read_rf does, so a test can speak in raw register bits.
    """

    def __init__(self, reader=None):
        self.writes = []
        self._reader = reader or (lambda path, addr, mask: 0xFFFFF)

    def write(self, t, path, addr, mask, data):
        self.writes.append((path, addr, mask, data))

    def read(self, t, path, addr, mask):
        return (self._reader(path, addr, mask) & mask) >> ((mask & -mask).bit_length() - 1)

    def writes_to(self, addr):
        return [w for w in self.writes if w[1] == addr]


def _bind(monkeypatch, rec):
    monkeypatch.setattr(rfk, "write_rf", rec.write)
    monkeypatch.setattr(rfk, "read_rf", rec.read)


def test_rck_triggers_rc_calibration_and_restores_rsv1(monkeypatch):
    def reader(path, addr, mask):
        if addr == rfk.RR_RSV1:
            return 0x12345
        if addr == rfk.RR_RCKS:
            return 1 << 3                      # cal done, do not spin
        if addr == rfk.RR_RCKC:
            return 0x0A << 10                  # trimmed value
        return 0

    rec = RFRecorder(reader)
    _bind(monkeypatch, rec)
    rfk.rck(MagicMock())

    for path in (0, 1):
        pw = [w for w in rec.writes if w[0] == path]
        assert pw[0] == (path, rfk.RR_RSV1, rfk.RR_RSV1_RST, 0)          # reset before calibrating
        assert (path, rfk.RR_MOD, rfk.RR_MOD_MASK, rfk.RR_MOD_V_RX) in pw  # RX mode
        assert (path, rfk.RR_RCKC, rfk.RFREG_MASK, 0x00240) in pw          # trigger
        assert (path, rfk.RR_RCKC, rfk.RFREG_MASK, 0x0A) in pw             # trimmed value kept
        assert pw[-1] == (path, rfk.RR_RSV1, rfk.RFREG_MASK, 0x12345)      # restored last


def test_lck_pulses_the_lock_trigger_with_the_current_cfgch(monkeypatch):
    def reader(path, addr, mask):
        return 0x1234 if addr == rfk.RR_CFGCH else 0

    rec = RFRecorder(reader)
    _bind(monkeypatch, rec)
    rfk.lck(MagicMock())

    assert rec.writes == [
        (0, rfk.RR_LCK_TRG, rfk.RR_LCK_TRGSEL, 1),
        (0, rfk.RR_CFGCH, rfk.RFREG_MASK, 0x1234),
        (0, rfk.RR_LCK_TRG, rfk.RR_LCK_TRGSEL, 0),
    ]


def test_lck_covers_both_paths_under_dbcc(monkeypatch):
    rec = RFRecorder(lambda path, addr, mask: 0x11 if addr == rfk.RR_CFGCH else 0)
    _bind(monkeypatch, rec)
    rfk.lck(MagicMock(), dbcc_en=True)

    assert {w[0] for w in rec.writes_to(rfk.RR_CFGCH)} == {0, 1}
    assert len(rec.writes_to(rfk.RR_LCK_TRG)) == 4


def test_rx_dck_skips_the_idac_when_the_check_bit_is_clear(monkeypatch):
    def reader(path, addr, mask):
        if addr == rfk.RR_DCK1:
            return rfk.RR_DCK1_DONE          # toggle completes
        if addr == rfk.RR_RSV1:
            return 0x0BEEF
        return 0                             # RR_DCKC_CHK stays clear

    rec = RFRecorder(reader)
    _bind(monkeypatch, rec)
    rfk.rx_dck(MagicMock())

    assert rec.writes_to(rfk.RR_RXBB2) == []
    for path in (0, 1):
        pw = [w for w in rec.writes if w[0] == path]
        assert (path, rfk.RR_MOD, rfk.RR_MOD_LO_SEL, 0) in pw   # single MAC: no dbcc LO offset
        assert pw[-1] == (path, rfk.RR_RSV1, rfk.RFREG_MASK, 0x0BEEF)


def test_rx_dck_folds_a_large_residual_into_the_idac(monkeypatch):
    def reader(path, addr, mask):
        if addr == rfk.RR_DCK1:
            return rfk.RR_DCK1_DONE
        if addr == rfk.RR_DCKC:
            return rfk.RR_DCKC_CHK           # calibration ran, check the residual
        if addr == rfk.RR_DCK:
            return 3 << 5                    # RR_DCK_DONE = 3 (> 1)
        if addr == rfk.RR_MOD:
            return 0
        return 0

    rec = RFRecorder(reader)
    _bind(monkeypatch, rec)
    rfk.rx_dck(MagicMock())

    idac = [w for w in rec.writes if w[1] == rfk.RR_RXBB2 and w[2] == rfk.RR_RXBB2_IDAC]
    assert [(w[0], w[3]) for w in idac] == [(0, 3), (0, 1), (1, 3), (1, 1)]
    assert len(rec.writes_to(rfk.RR_DCK1)) == 2             # DCK1 cleared once per path


def test_rx_dck_recover_rewrites_a_drifting_offset(monkeypatch):
    """The LUT entry for a gain whose through-path offset differs from the bypassed measurement
    by more than 10 must be rewritten. [SRC] rtw8852c_rfk.c:1645-1668."""
    counters = {0: 0, 1: 0}

    def reader(path, addr, mask):
        if addr == rfk.RR_DCK1:
            return rfk.RR_DCK1_DONE
        if addr == rfk.RR_DCK:
            n = counters[path]
            counters[path] += 1
            # per gain: even_bs, odd_bs, even, odd (four RR_DCK reads). The bypassed pair reads 50
            # and the through pair reads 0, so |diff| > threshold and the bs value is kept.
            return (50 << 9) if n % 4 < 2 else 0
        return 0

    rec = RFRecorder(reader)
    _bind(monkeypatch, rec)
    rfk.rx_dck(MagicMock())

    rw = rec.writes_to(rfk.RR_LUTPLL)
    assert rw and rw[0][2] == rfk.RR_CAL_RW and rw[0][3] == 1
    assert rw[-1][3] == 0                                   # released again
    # val_i = 50 → halved to 25 in the LUT low field; val_q stayed 0.
    assert (0, rfk.RR_LUTWD0, rfk.RFREG_MASK, 25) in rec.writes


def test_rck_uses_calibrated_fallback_when_read_zero(monkeypatch):
    """When read_rf returns 0 on USB / timeout, RCK should use calibrated default trim (0x10) and ensure RST=1."""
    def reader(path, addr, mask):
        return 0  # simulates USB read returning 0

    rec = RFRecorder(reader)
    _bind(monkeypatch, rec)
    rfk.rck(MagicMock())

    for path in (0, 1):
        pw = [w for w in rec.writes if w[0] == path]
        assert pw[0] == (path, rfk.RR_RSV1, rfk.RR_RSV1_RST, 0)
        # Should keep fallback trim (0x00240 | (0x10 << 10))
        assert (path, rfk.RR_RCKC, rfk.RFREG_MASK, 0x00240 | (0x10 << 10)) in pw
        # Should restore RSV1 with RST=1 (not 0)
        assert pw[-1] == (path, rfk.RR_RSV1, rfk.RFREG_MASK, 1)


def test_init_runs_rck_then_rx_dck(monkeypatch):
    order = []
    monkeypatch.setattr(rfk, "rck", lambda t: order.append("rck"))
    monkeypatch.setattr(rfk, "rx_dck", lambda t, dbcc_en=False: order.append("rx_dck"))
    rfk.init(MagicMock())
    assert order == ["rck", "rx_dck"]
