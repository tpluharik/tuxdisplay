# Architecture

This document describes TuxDisplay 0.4.21. The project has two display backends and five receiver paths. The GNOME Wayland backend can either extend the current desktop or mirror its primary physical monitor.

## GNOME Wayland data flow

~~~text
GNOME Shell / Mutter
  ├─ Extend: virtual monitor (Meta-0)
  └─ Mirror: current primary physical monitor

Selected monitor
  └─ ScreenCast + PipeWire
       └─ GStreamer pipeline
            ├─ VA-API or x264 H.264 Annex B
            │    └─ OpenDisplay framing
            │         ├─ usbmuxd → USB cable → OpenDisplay on iPadOS
            │         └─ ADB forward → USB cable → OpenDisplay on Android
            └─ JPEG frames
                 ├─ Tight/JPEG VNC → ADB reverse → AVNC on Android
                 └─ authenticated HTTP/MJPEG → tablet browser

Pointer rendering
  ├─ default: embedded by Mutter → H.264 video → every receiver
  └─ optional: XWayland position → cursor + cursorImg → OpenDisplay overlay

OpenDisplay touch / Pencil / scroll or AVNC pointer / keyboard
  └─ guarded input translation
       └─ letterbox-aware coordinate mapping
            └─ Mutter RemoteDesktop input events → selected monitor
~~~

### Virtual monitor

`tuxdisplay-wayland` asks Mutter's display configuration API to create a virtual monitor with the configured width and height. GNOME owns the output and exposes it to normal display settings, so windows can be moved between physical monitors and `Meta-0`.

Mutter assigns a new serial number to each virtual output, so GNOME's normal monitor configuration cannot identify the next `Meta-0` as the same device. TuxDisplay stores the complete logical layout—positions, scales, transforms, and primary selection—under stable physical-monitor identities in `~/.config/tuxdisplay/monitor-layout.json`. On the next start it matches those identities to the current outputs and replaces only the changing `Meta-0` identity. If the active monitor set or supported scales no longer match, startup continues with Mutter's safe default placement.

The daemon observes Mutter's `MonitorsChanged` signal. After a user rearranges screens, it debounces the topology update, saves the complete layout, tears down only the stale GStreamer capture pipeline, and immediately reopens the same Mutter PipeWire node. It then primes OpenDisplay with the cached keyframe and requests a fresh IDR. The virtual monitor and USB session remain alive throughout the refresh.

Creating and removing the monitor changes the GNOME monitor topology. A resolution change therefore removes the old output and creates a new one; applications on the removed output may be returned to a physical monitor.

### Primary-screen mirror

When `DISPLAY_MODE=mirror`, `tuxdisplay-wayland` does not create `Meta-0`. It asks `org.gnome.Mutter.DisplayConfig` for the active logical monitors, selects the primary physical connector, and passes that connector to the ScreenCast session's `RecordMonitor` method. If GNOME does not mark a primary monitor, the first active physical connector is used. A virtual connector is never selected as the mirror source.

The stream parameters report the source size in compositor coordinates. TuxDisplay scales that source into the configured stream resolution with aspect ratio preserved and borders added when necessary. OpenDisplay and browser input arrives in encoded-raster coordinates; `map_letterboxed_point` removes the borders and maps the remaining point into the source-monitor coordinate space before the RemoteDesktop call. Touching a border clamps safely to the nearest desktop edge.

Switching between Extend and Mirror performs one explicit service restart. The physical monitor is never reconfigured or removed in Mirror mode.

### Capture and encoding

Mutter provides a damage-driven PipeWire stream for the selected virtual or physical monitor. One GStreamer pipeline accepts each changed frame immediately, emits the most recent buffer only once per second while the source is otherwise quiet as a liveness probe, scales it into the configured stream raster, and splits the frames:

- the preferred OpenDisplay branch uses VA-API H.264 plus GPU post-processing when `vah264enc` and `vapostproc` are available;
- the fallback branch uses zero-latency, sliced, multi-threaded x264;
- both encoders use constrained-baseline Annex B, no B-frames, sparse periodic IDRs plus on-demand keyframes, and a bitrate scaled from the selected pixel rate;
- VA-API uses variable bitrate so static or simple content does not consume the configured ceiling continuously;
- the compatibility branch produces JPEG frames for the authenticated MJPEG endpoint and Tight/JPEG AVNC server, and closes its valve while neither receiver is viewing.

Raw-frame queues hold at most one frame and leak downstream, so a slow encoder skips obsolete raw images instead of increasing latency. Encoded frames are never dropped independently because doing so would break the H.264 prediction chain: an encoded-queue overflow atomically discards the chain, gates transmission, and requests a fresh IDR. The selected 15, 30, or 60 FPS value caps the virtual monitor and advertised receiver cadence; it does not cause duplicate unchanged frames to be encoded at that rate. TuxDisplay caches the most recent keyframe to show a static desktop, but keeps later delta frames gated until a fresh session IDR arrives.

The default screen-cast asks Mutter to embed the cursor, ensuring it is visible even on receivers that implement only video. The optional low-power overlay asks for cursor metadata instead. On GNOME's XWayland session, TuxDisplay then polls the pointer position every 16 ms, maps it through the selected monitor's XRandR geometry, deduplicates unchanged samples, and sends the OpenDisplay `cursor` control message. A generated compact PNG arrow is sent once per connection as `cursorImg`. This optional mode keeps a static desktop at the low-rate liveness cadence during pointer movement, but it is suitable only for receivers that implement the optional cursor controls.

Annex-B start-code inspection uses native byte search and leaves already-normalized access units untouched. The OpenDisplay writer sends framing, telemetry, and the encoded access unit without concatenating another full-frame copy. Recent PipeWire capture rate, sender source rate, sent rate, pending frames, drops, and chain recoveries are saved beside receiver telemetry for `tuxdisplay status`. The sender advertises measured capture rate in its health ping rather than repeating the configured ceiling as if it were observed performance.

### Direct USB transport

TuxDisplay speaks the public OpenDisplay protocol version 3. For Apple devices, it asks usbmuxd to connect to port 9000 on a paired iPad. For Android devices, it asks ADB for a dynamic loopback port forward to TCP 9000 on one authorized device. Both paths receive the app's JSON hello, reply with the stream configuration, and send length-prefixed H.264 Annex-B access units. Control and input messages travel over the same connection.

The OpenDisplay transport is not IP networking. It does not require an address, DHCP, Personal Hotspot, Wi-Fi, or the optional USB gadget service.

TuxDisplay checks every attached Apple USB device and every ADB-authorized Android device. Apple candidates are tried through usbmuxd, followed by Android candidates through a serial-scoped ADB forward. Each temporary Android forward is removed after connection failure, disconnect, or shutdown. The sender validates the receiver hello and retries with a bounded backoff.

Receiver telemetry drives staged recovery: first request a fresh IDR, then rebuild the cable session if real packet loss or active-stream underperformance persists. OpenDisplay's decoder-starvation counter is retained for diagnostics but does not trigger recovery by itself because it is non-normative and receiver implementations may count stalls differently. Recovery evaluates packet loss and receiver rate only after the sender has produced a sufficient active sample.

The transport also tracks telemetry liveness separately from general control traffic. Once a receiver has sent a valid statistics report, eight seconds without another report during active video marks the saved counters stale, primes the cached keyframe, and requests a fresh IDR. At fifteen seconds the socket is shut down so both transport threads wake and the discovery loop establishes a new session. A receiver that never implements statistics does not arm this watchdog.

A GLib timer independently watches the encoded-frame callback. This covers a whole-pipeline hang where GStreamer and receiver telemetry stop simultaneously, because transport-only evidence cannot distinguish that failure. After eight seconds without an encoded frame, TuxDisplay records the stale pipeline and asks systemd for one non-blocking service recycle. A hardware-pipeline hang records a 24-hour software fallback. The state file retains a rolling ten-minute recovery window; two automatic recycles are allowed and a third is suppressed, preventing a persistent driver failure from turning into a virtual-monitor restart loop.

### AVNC compatibility transport

The Wayland daemon also binds a minimal RFB 3.8 server to `127.0.0.1:VNC_PORT`. It advertises Tight encoding and reuses the JPEG frame already produced for the browser branch, so it does not add another screen capture. The branch remains closed until an AVNC connection completes. Each framebuffer update is request-paced by the VNC client, preventing an unbounded sender queue.

The server requires the viewer to advertise both Tight encoding and a JPEG quality pseudo-encoding. It accepts display widths up to Tight's 2048-pixel rectangle limit; wider TuxDisplay presets remain available to OpenDisplay and the browser path, while AVNC reports an explicit unavailable state.

An `AndroidReverseManager` discovers ADB-authorized devices and applies `adb -s SERIAL reverse tcp:VNC_PORT tcp:VNC_PORT`. AVNC therefore connects to `127.0.0.1:5900` on Android even though the server runs on the laptop. The mapping is device-scoped and removed when TuxDisplay stops. It never binds VNC to a LAN interface.

The implemented RFB input subset covers absolute pointer motion, three buttons, vertical and horizontal wheel events, and keysyms. Disconnect releases tracked buttons and keys. The default embedded cursor remains part of each JPEG frame, so AVNC does not depend on OpenDisplay cursor extensions.

RFB security type `None` is deliberately limited to the loopback socket behind Android's USB-debugging authorization. This is a compatibility boundary, not application-layer encryption or per-session authentication. OpenDisplay remains the preferred path for H.264 efficiency, richer telemetry, and automatic frozen-receiver recovery.

### Input safety

OpenDisplay v3 touch messages do not include a touch-slot identifier. Mutter's native touch API requires balanced, uniquely identified slots. Sending the slot-less stream directly as native touch could create invalid compositor state; TuxDisplay 0.4.0 did so and could abort GNOME Shell. AVNC instead sends standard VNC pointer/button events and never enters Mutter's native multi-touch path.

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
Xvfb :48 → Openbox + tint2 → x11vnc ┬→ websockify/noVNC → browser
                                      └→ ADB reverse → AVNC on Android
~~~

The isolated desktop is not part of the user's current monitor layout. `tuxdisplay launch` can start applications inside it. The display number is specific to this backend; the VNC port is shared with the Wayland AVNC compatibility path. X11's x11vnc requires the displayed TuxDisplay PIN as its VNC password.

Set `TUXDISPLAY_FORCE_X11=1` in the user service environment to select this backend deliberately.

## Closed-lid inhibitor

When `KEEP_AWAKE_WITH_LID_CLOSED=1`, `tuxdisplay-session` re-executes itself below `systemd-inhibit` before selecting a display backend. The inhibitor blocks `sleep` and `handle-lid-switch` through logind and is owned by the TuxDisplay service process tree. Stopping or failing the service closes the inhibitor automatically, so no permanent system configuration is changed.

## Desktop application and updates

The manager and Ayatana application indicator are owned by one GTK 3 `Gtk.Application` with the ID `io.github.tuxdisplay.Manager`. The background login activation holds the application without opening a window; app-grid or tray activation presents the existing manager. The desktop filename matches the application ID so GNOME can associate the window, launcher, and packaged `tuxdisplay` icon.

Update checks are outside the display data path and fail silently during automatic offline checks. A stable update follows this flow:

~~~text
GitHub latest-release API
  └─ exact tuxdisplay_VERSION_all.deb + SHA256SUMS assets
       └─ HTTPS host and size validation
            └─ SHA-256 + optional GitHub asset-digest validation
                 └─ dpkg package/name/version/architecture validation
                      └─ explicit Install action → PolicyKit → apt-get
~~~

The display service does not require Internet access. Only checking for and downloading a release does.

## Optional USB network gadget

`tuxdisplay-usb` can configure Linux ConfigFS, CDC ECM, address `10.55.0.1/24`, and a private dnsmasq instance. This gives the browser fallback a cable network on computers with a USB Device Controller.

The helper is privileged and launched through PolicyKit or its disabled-by-default system service. Ordinary x86 laptop ports are usually host-only and cannot provide this function. Direct OpenDisplay USB works on normal host ports and is independent of gadget mode.

## Process and state model

| Component | Responsibility |
| --- | --- |
| `/usr/bin/tuxdisplay` | CLI, single-instance GTK manager/tray, verified updater, configuration, status, and service control |
| `tuxdisplay.service` | Per-user lifecycle for the selected display backend |
| `tuxdisplay-wayland` | Virtual-monitor or primary-monitor capture, encoding, browser server, and input |
| `display_source.py` | Primary physical-monitor selection and aspect-aware mirrored input mapping |
| `opendisplay_usb.py` | usbmuxd and ADB transports, OpenDisplay framing, reconnect, keyframe cache, and input translation |
| `video_pipeline.py` | Latest-frame pacing, bounded GStreamer branches, bitrate selection, and VA-API/x264 graphs |
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
| `~/.config/tuxdisplay/config` | Extend/mirror selection, resolution, frame rate, encoder preference, lid-close behavior, display number, and ports |
| `~/.config/tuxdisplay/password` | Browser PIN |
| `~/.config/tuxdisplay/*.rfb` | Browser/VNC authentication material when used |
| `~/.local/state/tuxdisplay/` | Connection state and logs |
| `/usr/share/tuxdisplay/` | Browser clients and X11 desktop configuration |

Per-user secrets and configuration are created with mode `0600`. Runtime files are owned by the desktop user.

## Design constraints

- Native extension and primary-screen mirroring are coupled to GNOME/Mutter's private ScreenCast, RemoteDesktop, and display-configuration interfaces.
- Hardware acceleration currently targets VA-API; systems without compatible elements or drivers use the software x264 fallback.
- Direct OpenDisplay discovery and transport currently use USB only: usbmuxd on iPadOS and ADB forwarding on Android.
- The configured resolution is fixed for a service run; receiver dimensions do not reconfigure the monitor.
- One direct OpenDisplay receiver is supported at a time.
- OpenDisplay protocol v3 has no application-level encryption or authentication.

See [the competitive analysis](COMPETITIVE_ANALYSIS.md) for how these constraints compare with adjacent projects and [the contributor guide](../CONTRIBUTING.md) for development checks.
