# TuxDisplay

TuxDisplay turns an iPad browser into a real extended monitor for a GNOME Wayland desktop. GNOME creates a compositor-owned virtual output, so windows can be dragged between the computer and iPad. Video and touch input travel over an authenticated local web connection.

The Debian package includes a standalone GTK manager, application icon, and GNOME tray indicator. Other Linux desktops retain an isolated X11/noVNC workspace as a compatibility fallback.

## Features

- Real `Meta-0` extended monitor on GNOME Wayland.
- Touch, pointer, scrolling, and keyboard input from Safari.
- Three tray states: disconnected, running/waiting, and connected.
- Tray actions to open the manager, start the display, connect USB, and close the connection.
- Direct USB networking through iPad tethering on normal PCs.
- USB gadget Ethernet on computers with a device-capable USB controller.
- PIN authentication with a private per-user configuration.

## Build

```sh
./build-deb.sh
```

The package is written to `dist/tuxdisplay_0.3.0_all.deb`.

## Install and use

```sh
sudo apt install ./dist/tuxdisplay_0.3.0_all.deb
tuxdisplay start
```

Open **TuxDisplay** from the application menu to manage the display without a terminal. The tray icon starts automatically at the next login and is also started whenever the manager opens.

The tray badge is gray when stopped, amber while waiting for an iPad, and green while an authenticated browser is viewing the monitor. Choose **Close connection** to stop streaming and remove the virtual monitor.

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

## Connect through a USB cable

### Normal laptop or desktop USB port

A normal PC USB port is a host port, and the iPad is the USB device. Stock iPad Safari needs an IP network over that cable, which iPadOS provides through Personal Hotspot:

1. Connect the iPad with a data-capable USB cable.
2. Tap **Trust** on the iPad if prompted.
3. On the iPad, enable **Settings → Personal Hotspot → Allow Others to Join**.
4. Open TuxDisplay and choose **Connect USB**.
5. Open the USB address shown by TuxDisplay in Safari.

TuxDisplay detects the trusted iPad with `libimobiledevice`, detects the `ipheth` cable interface, asks NetworkManager to connect it, and prefers the cable IP address automatically. Personal Hotspot is required by iPadOS even when cellular data is not being used for the display traffic.

### Device-capable USB port

Linux devices with a USB Device Controller can act as a CDC ECM Ethernet gadget. **Connect USB** configures `10.55.0.1/24` through a PolicyKit prompt. It can also be managed manually:

```sh
sudo systemctl enable --now tuxdisplay-usb-gadget.service
```

Most x86 laptop ports cannot use gadget mode; use iPad tethering above on those systems.

## Configuration

`~/.config/tuxdisplay/config` supports:

```ini
RESOLUTION=1920x1080
DISPLAY_NUMBER=48
WEB_PORT=6080
VNC_PORT=5900
```

`DISPLAY_NUMBER` and `VNC_PORT` apply only to the compatibility fallback. Restart TuxDisplay after changing resolution or port. Runtime state is kept in `~/.local/state/tuxdisplay/`, and the PIN is stored with user-only permissions in `~/.config/tuxdisplay/password`.

Set `TUXDISPLAY_FORCE_X11=1` in the user service environment to force the X11 workspace fallback.

## Security

- The browser must authenticate with the generated six-digit PIN.
- Stopping or closing the connection invalidates the current browser session.
- The server listens on local interfaces for LAN and USB access.
- Video and input use HTTP. Use a trusted private USB or LAN connection; do not expose port 6080 to the public Internet.

## Remove

```sh
sudo apt remove tuxdisplay
```

User configuration remains in `~/.config/tuxdisplay` after removal.
