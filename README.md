# TuxDisplay

TuxDisplay turns an iPad into a real USB-connected extended monitor for a GNOME Wayland desktop. GNOME creates a compositor-owned virtual output, so windows can be dragged between the computer and iPad. H.264 video and touch input travel directly to the free OpenDisplay iPad app through Apple's USB multiplexing protocol. No IP address, Internet connection, Wi-Fi, cellular service, or Personal Hotspot is required.

The Debian package includes a standalone GTK manager, application icon, and GNOME tray indicator. The authenticated Safari/browser receiver remains available as a network fallback. Other Linux desktops retain an isolated X11/noVNC workspace as a compatibility fallback.

## Features

- Real `Meta-0` extended monitor on GNOME Wayland.
- Direct OpenDisplay USB connection through `usbmuxd` on a normal laptop port.
- Low-latency H.264 with automatic reconnect and keyframe recovery.
- Touch, scrolling, and Apple Pencil input from OpenDisplay.
- Touch, pointer, scrolling, and keyboard input from the Safari fallback.
- Three tray states: disconnected, running/waiting, and connected.
- Tray actions to open the manager, start the display, connect USB, and close the connection.
- No Personal Hotspot, USB tethering, firewall rule, or cable IP address required for OpenDisplay.
- USB gadget Ethernet on computers with a device-capable USB controller.
- PIN authentication for the browser fallback with a private per-user configuration.

## Build

```sh
./build-deb.sh
```

The package is written to `dist/tuxdisplay_0.4.2_all.deb`.

## Install and use

```sh
sudo apt install ./dist/tuxdisplay_0.4.2_all.deb
tuxdisplay start
```

Install [OpenDisplay](https://apps.apple.com/us/app/opendisplay/id6780264891) from the App Store on the iPad. Open **TuxDisplay** from the Linux application menu to manage the display without a terminal. The tray icon starts automatically at the next login and is also started whenever the manager opens.

The tray badge is gray when stopped, amber while waiting for an iPad, and green while OpenDisplay or an authenticated browser is viewing the monitor. Choose **Close connection** to stop streaming and remove the virtual monitor.

Drag a window beyond the right edge of the primary display to place it on the iPad. Display placement can be changed in **Settings → Displays**.

Useful commands:

```sh
tuxdisplay start
tuxdisplay status
tuxdisplay url
tuxdisplay password
tuxdisplay password --reset
tuxdisplay restart
tuxdisplay stop
tuxdisplay usb status
tuxdisplay usb connect
tuxdisplay usb disconnect
tuxdisplay tray
tuxdisplay doctor
```

`tuxdisplay launch APPLICATION` launches an application in the current GNOME desktop. In fallback mode it launches into the isolated X11 workspace.

## Connect OpenDisplay through a USB cable

1. Install and open **OpenDisplay** on the iPad.
2. Connect a data-capable USB cable.
3. Unlock the iPad and tap **Trust** if prompted.
4. Open TuxDisplay and choose **Connect OpenDisplay**, or run `tuxdisplay usb connect`.
5. Drag a window beyond the right edge of the computer display.

TuxDisplay asks the local `usbmuxd` service for a transparent connection to OpenDisplay's port 9000. The iPad app sends its protocol greeting, TuxDisplay replies with the protocol version and video configuration, then streams one H.264 Annex-B access unit per framed message. OpenDisplay sends touch and scroll events back on the same cable connection.

The connection retries automatically when the cable is attached or OpenDisplay is reopened. Stopping TuxDisplay removes the virtual monitor and closes the cable connection.

## Browser fallback

The manager still shows a **Browser fallback URL** and PIN. Open that address in Safari when the iPad and computer already share a private network. USB tethering through Personal Hotspot and USB gadget Ethernet are supported for this fallback only; they are not needed by OpenDisplay.

### Optional device-capable USB network

Linux devices with a USB Device Controller can act as a CDC ECM Ethernet gadget. `tuxdisplay usb connect` configures `10.55.0.1/24` through a PolicyKit prompt when no trusted iPad is detected. It can also be managed manually:

```sh
sudo systemctl enable --now tuxdisplay-usb-gadget.service
```

Most x86 laptop ports cannot use gadget mode. Use the direct OpenDisplay transport on those systems.

## Configuration

`~/.config/tuxdisplay/config` supports:

```ini
RESOLUTION=1920x1080
DISPLAY_NUMBER=48
WEB_PORT=6080
VNC_PORT=5900
```

`DISPLAY_NUMBER` and `VNC_PORT` apply only to the X11 compatibility fallback. `WEB_PORT` and the PIN apply only to the browser fallback. Restart TuxDisplay after changing resolution or port. Runtime state is kept in `~/.local/state/tuxdisplay/`.

Set `TUXDISPLAY_FORCE_X11=1` in the user service environment to force the X11 workspace fallback.

## Security

- OpenDisplay runs over the local trusted-device USB channel. Protocol v3 itself is not encrypted or authenticated, so trust only computers you control.
- The browser fallback must authenticate with the generated six-digit PIN.
- Stopping or closing the connection invalidates the current browser session.
- The server listens on local interfaces for LAN and USB access.
- Video and input use HTTP. Use a trusted private USB or LAN connection; do not expose port 6080 to the public Internet.

## Remove

```sh
sudo apt remove tuxdisplay
```

User configuration remains in `~/.config/tuxdisplay` after removal.
