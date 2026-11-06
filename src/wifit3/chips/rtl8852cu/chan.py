"""RTL8852CU channel tuning (rtw8852c_set_channel).

Builds the rtw89_chan for a channel and tunes MAC/BB/RF registers.
[SRC] core.c:531 __rtw89_set_channel, rtw8852c.c:1943 set_channel.
"""
from . import phy
from .constants import RTW89_BAND_2G, RTW89_BAND_5G, RTW89_BAND_6G, RTW89_CHANNEL_WIDTH_20


def band_of(channel: int) -> int:
    """The band a channel number lives in. 2.4 GHz (1-14) and 5 GHz (36+)."""
    return RTW89_BAND_2G if channel <= 14 else RTW89_BAND_5G


def channel_to_freq(channel: int, band: int) -> int:
    """IEEE center frequency (MHz) for a channel. [SRC] ieee80211_channel_to_frequency."""
    if band == RTW89_BAND_2G:
        return 2484 if channel == 14 else 2407 + channel * 5
    if band == RTW89_BAND_6G:
        return 5950 + channel * 5
    return 5000 + channel * 5


def subband_of(channel: int, band: int) -> int:
    """Subband type according to Linux rtw89 chan.c rtw89_get_subband_type."""
    if band == RTW89_BAND_2G:
        return 0  # RTW89_CH_2G
    if band == RTW89_BAND_6G:
        return min(max(0, (channel - 1) // 32), 7)
    if 36 <= channel <= 64:
        return 1  # RTW89_CH_5G_BAND_1
    if 100 <= channel <= 144:
        return 3  # RTW89_CH_5G_BAND_3
    if 149 <= channel <= 177:
        return 4  # RTW89_CH_5G_BAND_4
    return 0


def make_chan(channel: int, band: int | None = None,
              bandwidth: int = RTW89_CHANNEL_WIDTH_20,
              primary_channel: int | None = None) -> dict:
    """rtw89_chan_create for monitor tuning."""
    b = band if band is not None else band_of(channel)
    pri = primary_channel if primary_channel is not None else channel
    return {
        "channel": channel,
        "primary_channel": pri,
        "band_type": b,
        "subband_type": subband_of(channel, b),
        "band_width": bandwidth,
        "freq": channel_to_freq(channel, b),
        "pri_sb_idx": 0,
    }


def set_channel(t, channel: int, band: int | None = None,
                bandwidth: int = RTW89_CHANNEL_WIDTH_20) -> dict:
    """Tune MAC, BB, and RF to the given channel, band and bandwidth."""
    chan = make_chan(channel, band=band, bandwidth=bandwidth)
    phy.set_channel(t, chan)
    return chan
