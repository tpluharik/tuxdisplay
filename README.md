# TuxDisplay

TuxDisplay turns an iPad or Android tablet into an extended monitor or a touch-controlled mirror of the primary screen on GNOME Wayland. It captures through Mutter and PipeWire, then streams over a normal USB data cable to OpenDisplay on iPadOS/Android or to the open-source AVNC client on Android.

No IP address, Internet connection, Wi-Fi, cellular service, Personal Hotspot, account, or special USB dongle is required for the preferred connection.

The Debian package also includes:

- one GTK application with a manager, three-state tray icon, and verified in-app updates;
- an offline AVNC compatibility path for Android using Tight/JPEG VNC over an automatic ADB reverse tunnel;
- an authenticated Safari/browser fallback for private networks;
- an isolated X11/noVNC workspace for desktops that cannot create a GNOME virtual monitor;
- an optional USB Ethernet gadget helper for hardware with a device-capable USB controller.

> [!IMPORTANT]
> Do not use TuxDisplay 0.4.0 on GNOME Wayland. Its direct touch path could abort the compositor. Version 0.4.3 can fail PipeWire startup, 0.4.4 can unnecessarily reconnect a healthy low-FPS session, 0.4.9 can stall capture while displays are rearranged, 0.4.11 can enter a virtual-monitor restart loop after a capture failure, 0.4.15 can leave stale receiver health, and 0.4.16 does not recover when the host encoder and receiver telemetry stop together. Install 0.4.21 or newer for the current stability, cursor, rendering-performance, and AVNC compatibility fixes.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security](docs/SECURITY.md)
- [Competitive analysis](docs/COMPETITIVE_ANALYSIS.md)
- [Contributing and releases](CONTRIBUTING.md)
- [`tuxdisplay(1)`](packaging/man/tuxdisplay.1) and [`tuxdisplay-usb(8)`](packaging/man/tuxdisplay-usb.8)

## Support matrix

| Host/session | Result | Preferred receiver |
| --- | --- | --- |
| GNOME on Wayland | Real extended monitor or primary-screen mirror managed by Mutter | OpenDisplay on iPadOS/Android; AVNC on Android over direct USB |
| GNOME on Wayland, private LAN | Extended monitor or primary-screen mirror | Safari/Chrome browser fallback |
| Xorg or another Wayland compositor | Separate isolated X11 workspace; not an extension of the current desktop | Browser/noVNC or AVNC on Android |
| Device-capable Linux hardware | Optional USB Ethernet for the browser fallback | Browser/noVNC |

The packaged and tested target is Debian/Ubuntu. Direct OpenDisplay uses usbmuxd for iPadOS and a device-scoped ADB port forward for Android. AVNC uses a device-scoped ADB reverse tunnel to a loopback-only VNC endpoint. Wi-Fi OpenDisplay discovery and streaming are not implemented.

## What works

- A real `Meta-0` extended monitor on GNOME Wayland.
- A touch-controlled mirror of the current primary physical monitor, without creating `Meta-0`.
- Direct OpenDisplay USB through Apple usbmuxd or an Android ADB tunnel.
- Open-source AVNC on Android through a loopback-only ADB reverse tunnel, including pointer, click, scroll, and keyboard input.
- Damage-driven low-latency H.264 with automatic VA-API acceleration, software fallback, adaptive bitrate, and keyframe-safe recovery.
- A compatible pointer embedded in the video by default, plus an optional low-power OpenDisplay cursor overlay.
- Remembered tablet placement and in-place video refresh after GNOME display rearrangement.
- Tap, drag, and scroll input from OpenDisplay, plus Apple Pencil-as-pointer on iPadOS.
- Pointer, scroll, touch, and keyboard input in the browser fallback.
- Gray stopped, amber waiting, and green connected tray states.
- Start, connect, disconnect, and manager actions from the tray.
- Authenticated browser access using a generated six-digit PIN.
- Optional closed-lid operation using a service-scoped system sleep inhibitor.

OpenDisplay protocol v3 does not identify individual touch slots. TuxDisplay therefore treats touch and Pencil events as a single guarded pointer stream. Native multi-touch gestures and Pencil pressure or tilt are not forwarded.

The 0.4.15 transport was validated on a real iPad USB session at 2048×1536 and 30 FPS with no reported frame drops or prediction-chain recoveries. Those counters included repeated unchanged frames and did not prove 30 distinct desktop updates per second. Version 0.4.17 reports the recent PipeWire capture rate separately and stops re-encoding the same static frame continuously. Version 0.4.18 introduced separate OpenDisplay cursor control messages; version 0.4.19 adds independent XWayland tracking and direct tablet-input echo, so normal pointer motion is not tied to the damage-driven video cadence.

## Install a release

Download the current `.deb` and `SHA256SUMS` from [GitHub Releases](https://github.com/tpluharik/tuxdisplay/releases/latest), then verify and install it:

~~~sh
sha256sum --ignore-missing --check SHA256SUMS
sudo apt install ./tuxdisplay_0.4.21_all.deb
~~~

The checksum file can include packages from several releases. The checksum for the package being installed must report `OK`.

Install one compatible receiver before going offline:

- iPadOS 15 or newer: [OpenDisplay for iPhone and iPad](https://github.com/peetzweg/opendisplay#iphone-app). The upstream project documents TestFlight and source-build installation; use the [App Store listing](https://apps.apple.com/us/app/opendisplay/id6780264891) where it is available.
- Android 8 or newer: download the current APK from [OpenDisplay Android releases](https://github.com/josepacelli/opendisplay-android/releases/latest). Use version 0.0.8 or newer on Android 12–13. Android may ask you to allow installation from the app that opens the APK.
- Android 5 or newer, open-source alternative: install [AVNC from F-Droid](https://f-droid.org/packages/com.gaurav.avnc/). AVNC is GPL-3.0-or-later and its [source is published on GitHub](https://github.com/gujjwal00/avnc).

## Connect the iPad

1. Open **TuxDisplay** from the Linux application menu and start the display.
2. Choose **Extend desktop** for a separate workspace or **Mirror main screen** to see and control the primary monitor.
3. Open **OpenDisplay** on the iPad.
4. Connect the iPad with a data-capable USB cable.
5. Unlock the iPad and choose **Trust** if prompted.
6. Choose **Connect tablet** in TuxDisplay.
7. In Extend mode, drag a window onto the tablet monitor. In Mirror mode, touch the iPad to control the mirrored desktop.

## Connect Android with OpenDisplay

1. On Android, enable **Developer options**, then enable **USB debugging**.
2. Install and open **OpenDisplay Android**.
3. Choose **Extend desktop** or **Mirror main screen** in TuxDisplay.
4. Connect the tablet or phone with a data-capable USB cable.
5. Unlock Android and approve **Allow USB debugging** for this computer. Selecting **Always allow** avoids repeating this step.
6. Start the display and choose **Connect tablet**.
7. In Extend mode, drag a window onto the tablet monitor. In Mirror mode, touch the tablet to control the mirrored desktop.

The ADB authorization is the cable trust mechanism. TuxDisplay allocates a loopback-only host port and forwards it through ADB to OpenDisplay port 9000 on that specific Android device. After the APK and Debian dependencies are installed, this path works without Internet, Wi-Fi, tethering, or an IP address.

## Connect Android with AVNC

AVNC is the maintained, easy-to-install open-source alternative. It uses the compatibility JPEG path rather than OpenDisplay's hardware H.264 protocol, so prefer OpenDisplay for the smoothest motion and lowest power use.

1. Install [AVNC from F-Droid](https://f-droid.org/packages/com.gaurav.avnc/).
2. Enable **Developer options → USB debugging** on Android.
3. Connect a data-capable USB cable, unlock Android, and approve this computer.
4. Start TuxDisplay and choose **Connect tablet**. TuxDisplay automatically creates the ADB reverse tunnel.
5. In AVNC, add a connection with host `127.0.0.1` and port `5900`. Leave username and password empty for the GNOME Wayland backend.
6. Connect and select AVNC's scaling mode that fits the whole desktop. Use its touchpad or touchscreen gesture mode for pointer control.

No Android IP address is involved: AVNC's localhost connection crosses the USB cable through ADB. In the isolated X11 fallback backend, enter the six-digit TuxDisplay PIN as AVNC's VNC password.

AVNC's Tight/JPEG transport supports TuxDisplay widths up to 2048 pixels. Use `2048x1536` or a smaller preset; the `2160x1620` preset remains available for OpenDisplay but TuxDisplay reports AVNC as unavailable at that width instead of sending a non-standard frame.

TuxDisplay is a single application: the manager window and tray controls share one process and one connection state. The tray starts automatically at the next login. Opening TuxDisplay from the app grid brings up the existing manager instead of starting another copy. It is gray when stopped, amber while waiting for a viewer, and green while the tablet is viewing the display. **Close connection** stops streaming and, in Extend mode, removes the virtual monitor.

## In-app updates

The manager checks GitHub Releases after it starts and shows **Install update** when a newer stable version is available. You can also choose **Check for updates** from the tray. Downloading an update requires Internet access, but using a configured tablet display does not.

Before requesting system authentication, TuxDisplay requires the exact versioned Debian package and `SHA256SUMS` from the official release, restricts downloads to HTTPS GitHub hosts, verifies the SHA-256 checksum and any GitHub asset digest, and checks the package name, version, and architecture. Installation uses the normal system package manager so dependencies and upgrades remain tracked by Debian/Ubuntu. Restart TuxDisplay from the offered button after installation.

Change the monitor arrangement in **Settings → Displays** if the virtual output is not on the expected edge. TuxDisplay remembers the complete logical layout using stable physical-monitor identities and reapplies it when Mutter creates a new `Meta-0` identity. Rearranging screens reopens capture on the same PipeWire node without recreating the virtual monitor or disconnecting the tablet.

## Extend or mirror

Choose a mode in the manager before starting the display:

- **Extend desktop** creates a separate `Meta-0` monitor. Windows can be moved between the computer and tablet, and TuxDisplay remembers the arrangement.
- **Mirror main screen** captures the physical monitor currently marked primary in GNOME. The tablet shows the same desktop and its tap, drag, scroll, and Pencil events control that monitor.

Changing the mode while TuxDisplay is running performs one controlled service restart, then OpenDisplay reconnects automatically. Mirror mode scales the primary monitor into the selected stream resolution without cropping. If the monitor and tablet use different aspect ratios, the video is letterboxed and input coordinates are mapped only to the visible desktop area.

## Resolution and tablet aspect ratio

Choose a preset in the manager before starting or reconnecting:

| Preset | Aspect | Typical use |
| --- | --- | --- |
| 1024×768 | 4:3 | Low bandwidth or older hardware |
| 1280×800 | 16:10 | Small widescreen workspace |
| 1366×768 | ~16:9 | Low-bandwidth widescreen |
| 1536×1152 | 4:3 | Balanced iPad motion and detail |
| 1920×1080 | 16:9 | Default |
| 2048×1536 | 4:3 | Most 4:3 iPads |
| 2160×1620 | 4:3 | Higher-detail 4:3 iPads |

TuxDisplay does not yet read the receiver's aspect ratio and select a mode automatically. A 4:3 preset fills most traditional iPad panels more closely than 16:9 or 16:10; many Android tablets fit a 16:10 preset better. A browser may still reserve chrome or apply safe-area insets.

Changing resolution restarts the display service and OpenDisplay reconnects. In Extend mode this also recreates the virtual monitor because Mutter cannot change that mode in place; TuxDisplay reapplies the saved relative placement when `Meta-0` returns. In Mirror mode the physical monitor is never removed—the selected value is only the encoded stream resolution.

## Closed-lid operation

Enable **Keep awake with lid closed** in the TuxDisplay manager when the tablet should remain usable after closing the laptop. TuxDisplay then blocks system sleep and lid-switch handling for exactly as long as its user service runs. Stopping TuxDisplay releases the inhibitor and restores normal sleep behavior.

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

This is the normal offline mode. For iPadOS, TuxDisplay asks the local usbmuxd service for a transparent connection to OpenDisplay port 9000. For Android, it discovers an authorized device with ADB and creates a dynamically allocated loopback port forward to the same receiver port. The app and host then exchange the public OpenDisplay protocol greeting; TuxDisplay sends framed H.264 Annex-B access units and receives pointer/scroll events on the same cable.

The connection retries when the cable is attached or OpenDisplay is reopened. It does not create a network interface and does not use the browser PIN. Android must remain authorized for USB debugging; no shell command is run on the Android device.

### AVNC over Android USB

TuxDisplay includes a small RFB 3.8 server bound only to the laptop's `127.0.0.1:5900`. For each ADB-authorized Android device it creates `adb reverse tcp:5900 tcp:5900`, allowing AVNC to reach the laptop by connecting to the tablet's own localhost address. The mapping is removed when TuxDisplay stops.

The server reuses the demand-driven browser JPEG branch and enables that branch only while AVNC or a browser is connected. It sends Tight/JPEG framebuffer updates and accepts standard VNC pointer, button, wheel, and keyboard messages. The embedded pointer remains visible without requiring a client-specific cursor extension.

This compatibility mode deliberately favors simplicity and client availability. JPEG conversion can consume more CPU and normally delivers fewer frames than the hardware-accelerated OpenDisplay H.264 path. RFB security type `None` is accepted only on the loopback endpoint behind ADB authorization; never expose or forward the VNC port to a LAN or the Internet.

### Browser fallback

The manager shows a **Browser fallback URL** and PIN. Open that URL in Safari only when the iPad and computer already share a trusted private network. GNOME Wayland sends an authenticated MJPEG view; the X11 compatibility mode uses authenticated noVNC/websockify.

Browser fullscreen depends on Safari/iPadOS. Use TuxDisplay's in-page fullscreen control, **Add to Home Screen**, or hide Safari's toolbar where supported. Browser fullscreen does not change the selected stream resolution.

### Optional USB Ethernet gadget

Linux devices with a USB Device Controller can expose a CDC ECM network at `10.55.0.1/24` for the browser fallback:

~~~sh
sudo systemctl enable --now tuxdisplay-usb-gadget.service
~~~

Most x86 laptop USB ports are host-only and cannot use gadget mode. This is expected and does not affect direct OpenDisplay USB.

## Configuration

TuxDisplay creates `~/.config/tuxdisplay/config` with private permissions:

~~~ini
DISPLAY_MODE=extend
RESOLUTION=1920x1080
FPS=30
ENCODER=auto
CURSOR_MODE=embedded
KEEP_AWAKE_WITH_LID_CLOSED=0
DISPLAY_NUMBER=48
WEB_PORT=6080
VNC_PORT=5900
~~~

`DISPLAY_MODE` accepts `extend` or `mirror`. `FPS` accepts `15`, `30`, or `60`; it is a ceiling for the virtual monitor and stream rather than a promise that GNOME will redraw unchanged content. `30` is the balanced default and `60` is intended for systems whose encoder and tablet can sustain it. `ENCODER=auto` prefers the VA-API H.264 encoder and GPU color conversion when available, then falls back to tuned multi-threaded x264; choose `software` only for compatibility troubleshooting. `CURSOR_MODE=embedded` keeps the pointer visible on every receiver; `overlay` avoids full-frame work during pointer-only movement but requires an OpenDisplay receiver that renders `cursor` and `cursorImg` control messages. TuxDisplay encodes new damage-driven PipeWire frames immediately and emits one liveness frame per second while the desktop is unchanged. VA-API uses variable bitrate, so a static screen no longer consumes a constant full-rate encode and USB stream. Every queue remains bounded to prevent stale-frame buildup, and `tuxdisplay status` reports PipeWire capture, sender, and receiver rates separately. `KEEP_AWAKE_WITH_LID_CLOSED=1` enables the service-lifetime sleep inhibitor; the default `0` preserves normal sleep behavior. `DISPLAY_NUMBER` applies only to the X11 compatibility workspace. `VNC_PORT` is used by AVNC on both backends; `WEB_PORT` and the PIN apply to browser access. Restart TuxDisplay after changing a value.

For a 4:3 iPad, `1536x1152` is the balanced preset: it still fills the panel but processes 44% fewer pixels than `2048x1536`. Use the manager or `tuxdisplay configure --resolution 1536x1152 --restart`. Keep `2048x1536` when text sharpness matters more than motion and power use.

For a healthy direct session, recent PipeWire capture, `source_fps`, `sent_fps`, and receiver FPS should broadly agree during sustained motion; all are expected to fall while the desktop is quiet. `queued` should remain small, and `drops` and `recoveries` should remain at zero. OpenDisplay's receiver counters are diagnostic rather than a formal performance contract; compare them with the sender rates and visible motion before treating an isolated counter as a failure. If a receiver that previously supplied health reports stops doing so, TuxDisplay 0.4.16 marks those counters stale, requests a fresh keyframe after about eight seconds, and reconnects the cable session after about fifteen seconds if rendering does not recover.

TuxDisplay 0.4.17 separately watches the host's encoded-frame callback. If both the sender and receiver stop together, it performs a bounded service recycle. A hardware-pipeline stall selects the software encoder for the next 24 hours. Automatic recovery is limited to two service recycles per ten minutes, so a persistent driver or PipeWire failure cannot recreate the old monitor restart loop. `tuxdisplay status` shows the active encoder and any pipeline fallback or suppressed recovery.

TuxDisplay 0.4.19 introduced an OpenDisplay pointer overlay that polls XWayland at up to 60 Hz, echoes tablet input immediately, and sends deduplicated `cursor` messages plus a small cursor sprite. Because the protocol permits receivers to ignore those optional messages, 0.4.20 defaults to **Visible in video (compatible)**. Select **Low-power OpenDisplay overlay** only after confirming the tablet app displays the pointer. `Cursor transport` in `tuxdisplay status` identifies the active path.

TuxDisplay 0.4.20 disables the browser conversion branch before its queue when no browser viewer is connected. Its one-second diagnostics separately report fresh PipeWire frames, frames surviving the latest-frame queue, completed H.264 frames, cable sends, and tablet renders. On the validated iPad USB session, sustained full-screen animation reached about 60 real FPS with zero sender drops at both 1536×1152 and 2048×1536; the lower 4:3 preset remains preferable when fan noise and power use matter.

TuxDisplay 0.4.21 adds AVNC without changing the preferred OpenDisplay pipeline. The JPEG branch now wakes for either a browser or AVNC client and remains closed during an OpenDisplay-only session. AVNC is a compatibility fallback; its VNC frame rate is request-paced and is not included in OpenDisplay sender or receiver telemetry.

Set `TUXDISPLAY_FORCE_X11=1` in the user service environment to force the isolated X11 fallback.

Runtime state and logs are stored below `~/.local/state/tuxdisplay/`. See [Troubleshooting](docs/TROUBLESHOOTING.md) before editing these files.

## Build and test

~~~sh
python3 -m unittest discover -s tests -v
./build-deb.sh
~~~

The package is written to `dist/tuxdisplay_0.4.21_all.deb`. The build script also regenerates `dist/SHA256SUMS`.

Development and release conventions are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Direct OpenDisplay traffic stays on a trusted usbmuxd channel or a loopback-only ADB forward, but protocol v3 does not add encryption or authentication. AVNC is reachable only through a host-loopback ADB reverse mapping and uses Android USB-debugging authorization as its trust boundary. Browser access uses a PIN over ordinary HTTP and must not be exposed to the public Internet. Read the [security model and recommendations](docs/SECURITY.md).

## Remove

~~~sh
sudo apt remove tuxdisplay
~~~

Per-user configuration remains in `~/.config/tuxdisplay/` so that reinstalling preserves the selected resolution and PIN.

## License and attribution

TuxDisplay is released under the [MIT License](LICENSE). It independently implements the public [OpenDisplay protocol](https://github.com/peetzweg/opendisplay/blob/main/PROTOCOL.md) and the RFB/Tight JPEG subset used by AVNC; it is not affiliated with Apple, Google, OpenDisplay, or AVNC. The OpenDisplay Android receiver and AVNC are separate GPL-3.0-family projects.
