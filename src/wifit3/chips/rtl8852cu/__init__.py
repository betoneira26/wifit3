from wifit3.models.device_id import DeviceID

# [SRC] rtw8852cu.c:108-132 rtw_8852cu_id_table (kernel master, post-6.18).
SUPPORTED_IDS = [
    DeviceID(vid=0x0411, pid=0x03a6, chipset="RTL8852CU"),
    DeviceID(vid=0x056e, pid=0x4024, chipset="RTL8852CU"),
    DeviceID(vid=0x0bda, pid=0xc832, chipset="RTL8852CU"),
    DeviceID(vid=0x0bda, pid=0xc85a, chipset="RTL8852CU"),
    DeviceID(vid=0x0bda, pid=0xc85d, chipset="RTL8852CU"),
    DeviceID(vid=0x0db0, pid=0x991d, chipset="RTL8852CU"),
    DeviceID(vid=0x2c7c, pid=0x8206, chipset="RTL8852CU"),
    DeviceID(vid=0x35b2, pid=0x0502, chipset="RTL8852CU"),
    DeviceID(vid=0x35bc, pid=0x0101, chipset="RTL8852CU"),
    DeviceID(vid=0x35bc, pid=0x0102, chipset="RTL8852CU"),
    DeviceID(vid=0x37ad, pid=0x0103, chipset="RTL8852CU"),
    # Valve Deck variant: quirks DISABLE_2GHZ + LED GPIOs. [SRC] rtw8852cu.c:96-103
    DeviceID(vid=0x28de, pid=0x2432, chipset="RTL8852CU"),
]


def import_driver():
    from .driver import RTL8852CUDriver
    return RTL8852CUDriver
