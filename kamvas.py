import subprocess
import usb.core
import usb.util
import sys
from evdev import UInput, ecodes, AbsInfo

PEN_MAX_X = 86970
PEN_MAX_Y = 47752
PEN_MAX_Z = 8191
RESOLUTION = 5080
WIDTH = 1920
HEIGHT = 1080

def main():
    device = load_device()
    endpoint = register_endpoint(device)
    vpen = get_pen()
    map_tablet_coordinates(3840, 1080)
    print('Huion Kamvas GT191 driver is now running')

    listen_for_events(device, endpoint, vpen)

def load_device():
    device = usb.core.find(idVendor=0x256c, idProduct=0x006e)
    if not device:
        print("Could not find device. Run 'lsusb' and look for 'ID 0x256c:006e'", file=sys.stderr)
        sys.exit(1)

    return device

def register_endpoint(device):
    endpoint = None
    for config in device:
        for interface in config:
            for e in interface:
                if not endpoint:
                    endpoint = e

            if device.is_kernel_driver_active(interface.index):
                device.detach_kernel_driver(interface.index)
                usb.util.claim_interface(device, interface.index)
                print(f'Grabbed interface {interface.index}')

    return device[0][(0,0)][0]

def get_pen():
    cap_pen = {
        ecodes.EV_KEY: [
            ecodes.BTN_TOUCH, 
            ecodes.BTN_TOOL_PEN, 
            ecodes.BTN_STYLUS, 
            ecodes.BTN_STYLUS2
        ],
        ecodes.EV_ABS: [
            (ecodes.ABS_X, AbsInfo(0, 0, PEN_MAX_X, 0, 0, RESOLUTION)), #value, min, max, fuzz, flat, resolution
            (ecodes.ABS_Y, AbsInfo(0, 0, PEN_MAX_Y, 0, 0, RESOLUTION)),
            (ecodes.ABS_PRESSURE, AbsInfo(0, 0, PEN_MAX_Z, 0, 0, 0)),
        ],
    }   

    return UInput(events=cap_pen, name="kamvas-pen", version=0x3)

def listen_for_events(device, endpoint, vpen):
    while True:
        try:
            event = device.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize)
            data = parse_event(event)
            write_data_to_driver(vpen, data)

        except usb.core.USBError as ex:
            data = None
            if ex.args == ('Operation timed out',):
                print(ex, file=sys.stderr)
                continue

def parse_event(data):
    return {
        'x': (data[8] << 16) + (data[3] << 8) + data[2],
        'y': (data[5] << 8) + data[4],
        'pressure': (data[7] << 8) + data[6],
        'pen_is_touching': data[1] == 129,
        'btn1_pressed': data[1] == 130,
        'btn2_pressed': data[1] == 132
    }

def write_data_to_driver(vpen, data):
    vpen.write(ecodes.EV_ABS, ecodes.ABS_X, data['x'])
    vpen.write(ecodes.EV_ABS, ecodes.ABS_Y, data['y'])
    vpen.write(ecodes.EV_ABS, ecodes.ABS_PRESSURE, data['pressure'])
    vpen.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, data['pen_is_touching'] and 1 or 0)
    vpen.write(ecodes.EV_KEY, ecodes.BTN_STYLUS, data['btn1_pressed'] and 1 or 0)
    vpen.write(ecodes.EV_KEY, ecodes.BTN_STYLUS2, data['btn2_pressed'] and 1 or 0)
    vpen.syn()

def map_tablet_coordinates(width, height):
    main_screen_width = width
    main_screen_height = height

    # Set this to your tablet
    touch_screen_width = WIDTH
    touch_screen_height = HEIGHT

    # Below assumes that you have the tablet to the right of a single main screen, with extended desktop
    touch_screen_x_offset = main_screen_width
    touch_screen_y_offset = 0

    total_width = touch_screen_width + main_screen_width
    total_height = max(main_screen_height, touch_screen_height)

    # Compute coordinate transformation
    c0 = touch_screen_width / total_width
    c2 = touch_screen_height / total_height
    c1 = touch_screen_x_offset / total_width
    c3 = touch_screen_y_offset / total_height

    # [ c0 0  c1 ]
    # [ 0  c2 c3 ]
    # [ 0  0  1  ]
    flattened_matrix = [c0, 0.0, c1, 0.0, c2, c3, 0.0, 0.0, 1.0]

    # Execute change
    subprocess.call([
        "xinput",
        "set-prop",
        "kamvas-pen",
        "--type=float",
        "Coordinate Transformation Matrix",
        *list(map(str, flattened_matrix))
    ])

if __name__ == '__main__':
    main()

