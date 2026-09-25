# Architecture

This document describes TuxDisplay 0.4.6. The project has two display backends and three receiver paths. Only the GNOME Wayland backend extends the user's current desktop.

## GNOME Wayland data flow

~~~text
GNOME Shell / Mutter
  └─ virtual monitor (Meta-0)
       └─ ScreenCast + PipeWire
            └─ GStreamer pipeline
                 ├─ x264 H.264 Annex B
                 │    └─ OpenDisplay framing
                 │         └─ usbmuxd → USB cable → OpenDisplay on iPad
                 └─ JPEG frames
                      └─ authenticated HTTP/MJPEG → Safari on iPad

OpenDisplay touch / Pencil / scroll
  └─ guarded single-pointer translation
       └─ Mutter RemoteDesktop pointer events → Meta-0
~~~

### Virtual monitor

`tuxdisplay-wayland` asks Mutter's display configuration API to create a virtual monitor with the configured width and height. GNOME owns the output and exposes it to normal display settings, so windows can be moved between physical monitors and `Meta-0`.

Creating and removing the monitor changes the GNOME monitor topology. A resolution change therefore removes the old output and creates a new one; applications on the removed output may be returned to a physical monitor.

### Capture and encoding

Mutter provides a PipeWire stream for the virtual monitor. One GStreamer pipeline splits the captured frames:

- the OpenDisplay branch uses software x264 at 8 Mbit/s, byte-stream output, no B-frames, and an IDR interval of at most one second;
- the browser branch produces JPEG frames for the authenticated MJPEG endpoint and is paused while no browser is viewing.

Queues are deliberately small and leaky so latency is preferred over delivering stale frames. GNOME may supply PipeWire frames at a different rate from the requested virtual-monitor mode, so TuxDisplay accepts the negotiated source rate and uses a non-buffering pad probe to drop excess frames before conversion and encoding. This preserves the first damage-driven frame while keeping the configured 15, 30, or 60 FPS encoder cadence and receiver announcement. TuxDisplay caches the most recent H.264 keyframe to show a static desktop, but keeps delta frames gated until a fresh session IDR arrives.

### Direct USB transport

TuxDisplay speaks the public OpenDisplay protocol version 3. It asks usbmuxd to connect to port 9000 on a paired iPad, receives the app's JSON hello, replies with the stream configuration, and sends length-prefixed H.264 Annex-B access units. Control and input messages travel over the same connection.

The OpenDisplay transport is not IP networking. It does not require an address, DHCP, Personal Hotspot, Wi-Fi, or the optional USB gadget service.

TuxDisplay checks every attached Apple USB device, validates the receiver hello, and retries with a bounded backoff. Receiver telemetry drives staged recovery: first request a fresh IDR, then rebuild the cable session if real packet loss or active-stream underperformance persists. OpenDisplay's decoder-starvation counter is retained for diagnostics but does not trigger recovery because quiet damage-driven desktops can raise it during a healthy session.

### Input safety

OpenDisplay v3 touch messages do not include a touch-slot identifier. Mutter's native touch API requires balanced, uniquely identified slots. Sending the slot-less stream directly as native touch could create invalid compositor state; TuxDisplay 0.4.0 did so and could abort GNOME Shell.

Since 0.4.1, `OpenDisplayPointerTranslator` converts touch and Pencil phases into one guarded pointer/button stream:

- begin/down becomes pointer positioning plus one primary-button press;
- move becomes pointer motion;
- end/up becomes one primary-button release;
- scroll remains a bounded scroll event;
- duplicate begins and ends are suppressed;
- disconnect releases a possibly stuck button.

This supports tap, drag, scroll, and Pencil-as-pointer. It intentionally does not expose native multi-touch, Pencil pressure, or tilt.

## Browser receiver

On GNOME Wayland, the embedded HTTP service authenticates a six-digit PIN and serves the custom viewer plus an MJPEG stream. Pointer, touch, scroll, and keyboard events are returned to the remote-desktop session. A service-lifetime server-side token backs the authenticated browser cookie.

This path uses ordinary HTTP. It is a convenience fallback for trusted private networks, not an Internet-facing remote desktop.

## X11 compatibility backend

On Xorg or a compositor without the required Mutter APIs, `tuxdisplay-session` starts an isolated desktop:

~~~text
Xvfb :48 → Openbox + tint2 → x11vnc → websockify/noVNC → Safari
~~~

The isolated desktop is not part of the user's current monitor layout. `tuxdisplay launch` can start applications inside it. The display number and VNC port are configurable because they belong only to this backend.

Set `TUXDISPLAY_FORCE_X11=1` in the user service environment to select this backend deliberately.

## Closed-lid inhibitor

When `KEEP_AWAKE_WITH_LID_CLOSED=1`, `tuxdisplay-session` re-executes itself below `systemd-inhibit` before selecting a display backend. The inhibitor blocks `sleep` and `handle-lid-switch` through logind and is owned by the TuxDisplay service process tree. Stopping or failing the service closes the inhibitor automatically, so no permanent system configuration is changed.

## Optional USB network gadget

`tuxdisplay-usb` can configure Linux ConfigFS, CDC ECM, address `10.55.0.1/24`, and a private dnsmasq instance. This gives the browser fallback a cable network on computers with a USB Device Controller.

The helper is privileged and launched through PolicyKit or its disabled-by-default system service. Ordinary x86 laptop ports are usually host-only and cannot provide this function. Direct OpenDisplay USB works on normal host ports and is independent of gadget mode.

## Process and state model

| Component | Responsibility |
| --- | --- |
| `/usr/bin/tuxdisplay` | CLI, GTK manager, tray, configuration, status, and service control |
| `tuxdisplay.service` | Per-user lifecycle for the selected display backend |
| `tuxdisplay-wayland` | Virtual monitor, PipeWire capture, encoding, browser server, and input |
| `opendisplay_usb.py` | usbmuxd connection, OpenDisplay framing, reconnect, keyframe cache, and input translation |
| `tuxdisplay-session` | X11/Xvfb compatibility workspace |
| `/usr/sbin/tuxdisplay-usb` | Privileged optional USB Ethernet gadget |

The tray derives three user-facing states:

| State | Meaning |
| --- | --- |
| Disconnected | The user service is stopped |
| Running | The monitor exists and TuxDisplay is waiting for a receiver |
| Connected | OpenDisplay or an authenticated browser is actively viewing |

## Files and ownership

| Path | Contents |
| --- | --- |
| `~/.config/tuxdisplay/config` | Resolution, frame rate, lid-close behavior, display number, and ports |
| `~/.config/tuxdisplay/password` | Browser PIN |
| `~/.config/tuxdisplay/*.rfb` | Browser/VNC authentication material when used |
| `~/.local/state/tuxdisplay/` | Connection state and logs |
| `/usr/share/tuxdisplay/` | Browser clients and X11 desktop configuration |

Per-user secrets and configuration are created with mode `0600`. Runtime files are owned by the desktop user.

## Design constraints

- Native extension is coupled to GNOME/Mutter's private virtual-monitor interfaces.
- Encoding is currently software x264 rather than VA-API/NVENC/V4L2 hardware encoding.
- Direct OpenDisplay discovery and transport currently use USB only.
- The configured resolution is fixed for a service run; receiver dimensions do not reconfigure the monitor.
- One direct OpenDisplay receiver is supported at a time.
- OpenDisplay protocol v3 has no application-level encryption or authentication.

See [the competitive analysis](COMPETITIVE_ANALYSIS.md) for how these constraints compare with adjacent projects and [the contributor guide](../CONTRIBUTING.md) for development checks.
