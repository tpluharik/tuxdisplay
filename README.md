# TuxDisplay

TuxDisplay turns an iPad into a real extended monitor for a GNOME Wayland desktop. It creates a compositor-owned virtual output, captures that output with PipeWire, and streams H.264 directly to the free OpenDisplay iPad app over a normal USB data cable.

No IP address, Internet connection, Wi-Fi, cellular service, Personal Hotspot, account, or special USB dongle is required for the preferred connection.

The Debian package also includes:

- one GTK application with a manager, three-state tray icon, and verified in-app updates;
- an authenticated Safari/browser fallback for private networks;
- an isolated X11/noVNC workspace for desktops that cannot create a GNOME virtual monitor;
- an optional USB Ethernet gadget helper for hardware with a device-capable USB controller.

> [!IMPORTANT]
> Do not use TuxDisplay 0.4.0 on GNOME Wayland. Its direct touch path could abort the compositor. Version 0.4.3 can fail PipeWire startup, and 0.4.4 can unnecessarily reconnect a healthy low-FPS OpenDisplay session. Install 0.4.7 or newer.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security](docs/SECURITY.md)
- [Competitive analysis](docs/COMPETITIVE_ANALYSIS.md)
- [Contributing and releases](CONTRIBUTING.md)
- [`tuxdisplay(1)`](packaging/man/tuxdisplay.1) and [`tuxdisplay-usb(8)`](packaging/man/tuxdisplay-usb.8)

## Support matrix

| Host/session | Result | Preferred iPad receiver |
| --- | --- | --- |
| GNOME on Wayland | Real extended monitor managed by Mutter | OpenDisplay over direct USB |
| GNOME on Wayland, private LAN | Real extended monitor | Safari browser fallback |
| Xorg or another Wayland compositor | Separate isolated X11 workspace; not an extension of the current desktop | Safari/noVNC |
| Device-capable Linux hardware | Optional USB Ethernet for the browser fallback | Safari/noVNC |

The packaged and tested target is Debian/Ubuntu. The direct OpenDisplay sender currently uses usbmuxd only; Wi-Fi OpenDisplay discovery and streaming are not implemented.

## What works

- A real `Meta-0` extended monitor on GNOME Wayland.
- Direct OpenDisplay USB transport through Apple's usbmuxd protocol.
- H.264 video with reconnect, periodic IDR frames, and cached keyframe recovery.
- Tap, drag, scroll, and Apple Pencil-as-pointer input from OpenDisplay.
- Pointer, scroll, touch, and keyboard input in the browser fallback.
- Gray stopped, amber waiting, and green connected tray states.
- Start, connect, disconnect, and manager actions from the tray.
- Authenticated browser access using a generated six-digit PIN.
- Optional closed-lid operation using a service-scoped system sleep inhibitor.

OpenDisplay protocol v3 does not identify individual touch slots. TuxDisplay therefore treats touch and Pencil events as a single guarded pointer stream. Native multi-touch gestures and Pencil pressure or tilt are not forwarded.

## Install a release

Download the current `.deb` and `SHA256SUMS` from [GitHub Releases](https://github.com/tpluharik/tuxdisplay/releases/latest), then verify and install it:

~~~sh
sha256sum --ignore-missing --check SHA256SUMS
sudo apt install ./tuxdisplay_0.4.7_all.deb
~~~

The checksum file can include packages from several releases. The checksum for the package being installed must report `OK`.

Install [OpenDisplay](https://apps.apple.com/us/app/opendisplay/id6780264891) on the iPad.

## Connect the iPad

1. Open **TuxDisplay** from the Linux application menu and start the display.
2. Open **OpenDisplay** on the iPad.
3. Connect the iPad with a data-capable USB cable.
4. Unlock the iPad and choose **Trust** if prompted.
5. Choose **Connect OpenDisplay** in TuxDisplay.
6. Drag a window beyond the right edge of the computer display.

TuxDisplay is a single application: the manager window and tray controls share one process and one connection state. The tray starts automatically at the next login. Opening TuxDisplay from the app grid brings up the existing manager instead of starting another copy. It is gray when stopped, amber while waiting for a viewer, and green while the iPad is viewing the display. **Close connection** stops streaming and removes the virtual monitor.

## In-app updates

The manager checks GitHub Releases after it starts and shows **Install update** when a newer stable version is available. You can also choose **Check for updates** from the tray. Downloading an update requires Internet access, but using the iPad display does not.

Before requesting system authentication, TuxDisplay requires the exact versioned Debian package and `SHA256SUMS` from the official release, restricts downloads to HTTPS GitHub hosts, verifies the SHA-256 checksum and any GitHub asset digest, and checks the package name, version, and architecture. Installation uses the normal system package manager so dependencies and upgrades remain tracked by Debian/Ubuntu. Restart TuxDisplay from the offered button after installation.

Change the monitor arrangement in **Settings → Displays** if the virtual output is not on the expected edge.

## Resolution and iPad aspect ratio

Choose a preset in the manager before starting or reconnecting:

| Preset | Aspect | Typical use |
| --- | --- | --- |
| 1024×768 | 4:3 | Low bandwidth or older hardware |
| 1280×800 | 16:10 | Small widescreen workspace |
| 1366×768 | ~16:9 | Low-bandwidth widescreen |
| 1920×1080 | 16:9 | Default |
| 2048×1536 | 4:3 | Most 4:3 iPads |
| 2160×1620 | 4:3 | Higher-detail 4:3 iPads |

TuxDisplay does not yet read the iPad's aspect ratio and select a mode automatically. A 4:3 preset fills most traditional iPad panels more closely than 16:9 or 16:10. Safari and iPadOS may still reserve browser chrome or apply safe-area insets.

Changing resolution restarts the virtual monitor. The image will pause briefly, OpenDisplay will reconnect, and GNOME may move windows from the removed virtual monitor back to the laptop display. Move them back after the new monitor appears. If the iPad keeps the last frame, reopen OpenDisplay or use **Close connection**, then start again.

## Closed-lid operation

Enable **Keep awake with lid closed** in the TuxDisplay manager when the iPad should remain usable after closing the laptop. TuxDisplay then blocks system sleep and lid-switch handling for exactly as long as its user service runs. Stopping TuxDisplay releases the inhibitor and restores normal sleep behavior.

This option also blocks manual and idle suspend while TuxDisplay is running. A closed laptop can retain more heat, so keep it connected to power when appropriate and make sure its vents are not obstructed. Firmware-level thermal shutdown and critical-battery actions can still override the inhibitor.

## Command line

~~~sh
tuxdisplay                 # open the manager
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
tuxdisplay tray             # compatibility alias for the same background application
tuxdisplay doctor
tuxdisplay launch APPLICATION [ARGUMENT ...]
~~~

In GNOME Wayland mode, `launch` starts the application in the current desktop. In fallback mode, it starts the application in the isolated X11 workspace.

## Connection modes

### Direct OpenDisplay USB

This is the normal offline mode. TuxDisplay asks the local usbmuxd service for a transparent connection to OpenDisplay port 9000. The app and host exchange the public OpenDisplay protocol greeting, then TuxDisplay sends framed H.264 Annex-B access units and receives pointer/scroll events on the same cable.

The connection retries when the cable is attached or OpenDisplay is reopened. It does not create a network interface and does not use the browser PIN.

### Browser fallback

The manager shows a **Browser fallback URL** and PIN. Open that URL in Safari only when the iPad and computer already share a trusted private network. GNOME Wayland sends an authenticated MJPEG view; the X11 compatibility mode uses authenticated noVNC/websockify.

Browser fullscreen depends on Safari/iPadOS. Use TuxDisplay's in-page fullscreen control, **Add to Home Screen**, or hide Safari's toolbar where supported. Browser fullscreen does not change the virtual monitor resolution.

### Optional USB Ethernet gadget

Linux devices with a USB Device Controller can expose a CDC ECM network at `10.55.0.1/24` for the browser fallback:

~~~sh
sudo systemctl enable --now tuxdisplay-usb-gadget.service
~~~

Most x86 laptop USB ports are host-only and cannot use gadget mode. This is expected and does not affect direct OpenDisplay USB.

## Configuration

TuxDisplay creates `~/.config/tuxdisplay/config` with private permissions:

~~~ini
RESOLUTION=1920x1080
FPS=30
KEEP_AWAKE_WITH_LID_CLOSED=0
DISPLAY_NUMBER=48
WEB_PORT=6080
VNC_PORT=5900
~~~

`FPS` accepts `15`, `30`, or `60` and controls the requested virtual-monitor cadence, a non-buffering capture limiter, the encoder keyframe interval, and the advertised OpenDisplay cadence; `30` is the stability-oriented default. TuxDisplay accepts the actual PipeWire rate chosen by GNOME and safely drops excess frames before encoding. `KEEP_AWAKE_WITH_LID_CLOSED=1` enables the service-lifetime sleep inhibitor; the default `0` preserves normal sleep behavior. `DISPLAY_NUMBER` and `VNC_PORT` apply only to the X11 compatibility workspace. `WEB_PORT` and the PIN apply only to browser access. Restart TuxDisplay after changing a value.

Set `TUXDISPLAY_FORCE_X11=1` in the user service environment to force the isolated X11 fallback.

Runtime state and logs are stored below `~/.local/state/tuxdisplay/`. See [Troubleshooting](docs/TROUBLESHOOTING.md) before editing these files.

## Build and test

~~~sh
python3 -m unittest discover -s tests -v
./build-deb.sh
~~~

The package is written to `dist/tuxdisplay_0.4.7_all.deb`. The build script also regenerates `dist/SHA256SUMS`.

Development and release conventions are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Direct OpenDisplay traffic stays on the trusted usbmuxd cable channel, but protocol v3 does not add encryption or authentication. Browser access uses a PIN over ordinary HTTP and must not be exposed to the public Internet. Read the [security model and recommendations](docs/SECURITY.md).

## Remove

~~~sh
sudo apt remove tuxdisplay
~~~

Per-user configuration remains in `~/.config/tuxdisplay/` so that reinstalling preserves the selected resolution and PIN.

## License and attribution

TuxDisplay is released under the [MIT License](LICENSE). It independently implements the public [OpenDisplay protocol](https://github.com/peetzweg/opendisplay/blob/main/PROTOCOL.md); it is not affiliated with Apple or the OpenDisplay project.
