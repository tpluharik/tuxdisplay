# Troubleshooting

Start with:

~~~sh
tuxdisplay status
tuxdisplay usb status
tuxdisplay doctor
systemctl --user status tuxdisplay.service
journalctl --user -u tuxdisplay.service --since "10 minutes ago"
~~~

The first three commands are safe to paste into a bug report. Review logs before sharing them and remove usernames, hostnames, IP addresses, tablet identifiers, and the browser PIN.

## Do not run 0.4.0 on GNOME Wayland

TuxDisplay 0.4.0 could send invalid native touch state to Mutter and abort GNOME Shell. TuxDisplay 0.4.3 could reject GNOME's negotiated PipeWire rate, 0.4.4 could periodically reconnect a healthy low-FPS stream, 0.4.9 could leave the GStreamer pipeline in a pending state after displays were rearranged, 0.4.11 could repeatedly recreate the virtual monitor after a capture failure, 0.4.15 could leave stale receiver health, and 0.4.16 could miss a simultaneous host-pipeline and receiver freeze. Upgrade to 0.4.22 or newer for the current stability, cursor, rendering-performance, and AVNC compatibility fixes:

~~~sh
sudo apt install ./tuxdisplay_0.4.22_all.deb
tuxdisplay restart
~~~

Version 0.4.1 introduced guarded pointer translation. Version 0.4.2 added cached-keyframe recovery for static first frames. Version 0.4.3 added fresh-IDR gating, receiver-health recovery, and bounded shutdown. Version 0.4.4 accepts GNOME's negotiated PipeWire rate. Version 0.4.5 prevents false watchdog reconnects on quiet or low-FPS desktops. Version 0.4.6 adds optional closed-lid operation. Version 0.4.7 unifies the desktop application and adds verified in-app updates. Version 0.4.8 adds Android OpenDisplay over an ADB USB tunnel. Version 0.4.9 introduced monitor-placement persistence. Version 0.4.10 keeps PipeWire running during layout refresh. Version 0.4.11 restores the complete validated layout instead of reconstructing the tablet from one anchor. Version 0.4.12 suppresses duplicate topology events, settles real changes before refreshing capture, and prevents service failures from creating a virtual-monitor restart loop. Version 0.4.13 adds touch-controlled primary-screen mirroring. Version 0.4.14 adds automatic hardware encoding and a bounded low-latency video path. Version 0.4.15 added fixed-rate latest-frame pacing. Version 0.4.16 detects a receiver whose video telemetry freezes while its control channel remains alive. Version 0.4.17 adds independent host-pipeline recovery, a bounded automatic software fallback, and damage-driven variable-bitrate encoding to reduce duplicate work. Version 0.4.18 separates the cursor from video. Version 0.4.19 independently tracks physical pointer movement, echoes tablet input through the cursor overlay, discards cursor-only capture buffers, and adds a balanced 1536×1152 iPad preset. Version 0.4.20 removes inactive browser-branch work, reports every rendering stage once per second, and prevents standalone diagnostics from launching a duplicate managed service. Version 0.4.21 adds the AVNC Android USB compatibility transport. Version 0.4.22 aligns all package, application, documentation, and update metadata with the validated AVNC release candidate.

## Motion on the tablet is jumpy

Open the manager and leave **Video acceleration** on **Automatic (hardware preferred)**. Then run `tuxdisplay status` while moving a window or scrolling on the tablet. `Capture rate` is recent PipeWire output, `source_fps` is encoded H.264 entering the USB sender, `sent_fps` is the rate written to the cable, and the receiver line is OpenDisplay's own non-normative telemetry. Version 0.4.17 reports these separately so repeated or quiet frames cannot be mistaken for fresh desktop updates.

At a configured 30 FPS, values around 29–30 FPS during sustained motion are normal because the sender and receiver sample over independent time windows. The rates intentionally fall toward the one-frame-per-second liveness cadence while the desktop is static. A healthy session normally has `queued` near zero and keeps `drops=0` and `recoveries=0`.

Version 0.4.20 defaults to **Visible in video (compatible)** because OpenDisplay cursor controls are optional and some receiver builds ignore them. If the pointer is missing, select that mode in the manager or run `tuxdisplay configure --cursor-mode embedded --restart`. The optional **Low-power OpenDisplay overlay** should show `Cursor transport: mode=xwayland-poll`; its update count should rise while the pointer moves over the tablet even when video rates stay near the static cadence. If it reports `pipewire-metadata`, XWayland cursor polling was unavailable. For smoother full-window motion on a 4:3 iPad, select `1536x1152` in the manager or run `tuxdisplay configure --resolution 1536x1152 --restart`.

If receiver health changes to `stale=True`, TuxDisplay has stopped trusting the displayed receiver counters. It first sends a cached frame and requests a fresh IDR. If a valid report does not return within roughly seven more seconds, the USB session reconnects automatically; manually restarting the whole display service should no longer be necessary.

If sender and receiver health both stop updating, version 0.4.17 treats the encoded-frame callback as stalled after eight seconds and recycles the service. When this happens on the hardware encoder, the restarted service uses software encoding for 24 hours. If diagnostics show `recovery=suppressed`, two automatic pipeline recoveries already occurred in ten minutes; TuxDisplay leaves the service stable instead of entering a restart loop. Stop it, collect the service log, and investigate PipeWire or the graphics driver before retrying.

- If `drops=0`, `recoveries=0`, and sender and receiver rates agree during motion, the USB transport is healthy.
- If `source_fps` is low during motion, select 30 FPS or a smaller resolution such as 1024×768.
- If `source_fps` is healthy but `sent_fps` is lower or recoveries rise, reconnect with another data-capable cable or USB port.
- If automatic acceleration falls back to software, confirm the VA-API GStreamer elements are installed and usable; `tuxdisplay doctor` and the service log identify the active encoder.

The 60 FPS option is deliberately not the default. At 2048×1536 it requires roughly twice the encode work and bitrate of 30 FPS; use it only when live sender telemetry remains stable. If the manager says 60 FPS but `source_fps` remains much lower during sustained motion, the host encoder cannot maintain that preset. Use 30 FPS or reduce the resolution rather than accepting inconsistent motion.

## OpenDisplay shows a black screen

1. Confirm `tuxdisplay status` reports GNOME Wayland mode and a running service.
2. Confirm the package version is at least 0.4.8 when using Android.
3. Check that `Capture rate` and `Sender health` appear after the receiver connects. On 0.4.17 or newer, a static desktop produces a low-rate liveness frame instead of continuously consuming the configured FPS ceiling.
4. Close and reopen OpenDisplay so the sender performs a new handshake.
5. Run `tuxdisplay restart` if the app does not reconnect.

If a new connection remains black on the current version, capture the user-service log. The log should show a valid OpenDisplay hello, an active H.264 stream, and receiver-health statistics.

## The in-app update fails

Display streaming works offline, but checking for or downloading an update requires an Internet connection to GitHub. A failed automatic check does not affect the monitor.

1. Open the manager or tray and choose **Check for updates** again after Internet access is restored.
2. Confirm the system date is correct so HTTPS certificates validate.
3. Approve the system authentication prompt when installing.
4. Close another package manager if it is holding the Debian/Ubuntu package lock.
5. If verification fails, do not bypass it. Download the `.deb` and `SHA256SUMS` from the same GitHub release and verify them manually.

After a successful install, choose **Restart TuxDisplay**. If the old window remains, quit TuxDisplay from the tray and open it again from the application menu.

## The app icon is missing or two TuxDisplay windows appear

Version 0.4.7 registers the desktop launcher with the same ID as the GTK application and runs the manager and tray as one singleton. Log out and back in after upgrading so the old autostart process is replaced. If the desktop shell still caches an old launcher, remove it from favorites and add TuxDisplay again from the app grid.

## The display stops when the laptop lid closes

Enable **Keep awake with lid closed** in the TuxDisplay manager. The manager restarts the display once so the service can acquire its logind inhibitor. Confirm it with `tuxdisplay status`; the output should say that lid-close sleep is blocked while TuxDisplay runs.

The inhibitor is released when TuxDisplay stops. It intentionally blocks manual and idle suspend as well as lid-triggered sleep, but firmware thermal protection and critical-battery handling may still shut down or suspend the computer. Keep a closed laptop ventilated.

## The image freezes after rearranging displays

Version 0.4.12 listens for GNOME monitor-topology changes, saves the complete logical layout under stable monitor identities, and reopens capture on the same Mutter PipeWire node. It ignores duplicate notifications and waits for a burst of real changes to settle before doing one refresh. It keeps the virtual monitor and USB connection alive, primes OpenDisplay with a cached frame, and requests a fresh H.264 keyframe. Upgrade if rearranging screens leaves the tablet on its previous frame.

On 0.4.12 or newer, wait about two seconds after pressing **Apply** in GNOME Displays. The log should contain one `monitor arrangement changed; refreshing the video stream` line. If the image remains frozen, stop TuxDisplay before collecting the service log; the service will not restart itself or recreate the virtual monitor.

## The image pauses after changing TuxDisplay resolution

A resolution change restarts the video service. During that transition the tablet can continue displaying its last decoded frame. Extend mode also recreates the virtual monitor; Mirror mode leaves the physical monitor unchanged and only changes the encoded stream raster.

1. Wait a few seconds for the amber tray state to return.
2. Reopen OpenDisplay if it did not reconnect.
3. If necessary, choose **Close connection**, start TuxDisplay again, and reconnect.
4. In Extend mode, look on the laptop display for applications GNOME moved away from the removed virtual output. TuxDisplay will restore the saved monitor placement when `Meta-0` returns.

This is a lifecycle limitation, not a tablet network problem. Dynamic in-place mode switching is not implemented.

## Mirror mode shows the wrong monitor

**Mirror main screen** captures the physical monitor marked primary in GNOME when TuxDisplay starts. Open **Settings → Displays**, select the intended monitor as primary, and restart TuxDisplay. The mirror path never selects the virtual `Meta-0` connector.

If the image has borders, choose a stream resolution with an aspect ratio closer to the primary monitor. Borders preserve the complete desktop instead of cropping it. Touches inside the visible image are mapped back to the physical monitor; touching a border safely targets the nearest screen edge.

## The image does not fill the tablet

The default 1920×1080 mode is 16:9. Most traditional iPads are closer to 4:3, so select 2048×1536 or 2160×1620. Many Android tablets are closer to 16:10, so try 1280×800. Use 1024×768 if performance matters more than detail. In Mirror mode, the source monitor is fitted inside this stream resolution without cropping, so a source/stream aspect-ratio mismatch intentionally produces borders.

TuxDisplay does not yet negotiate the receiver's native dimensions. Browser chrome and OS safe areas can also leave borders even when the aspect ratio matches.

## iPad cable detected, but OpenDisplay does not connect

Check each item:

- The cable supports data, not charging only.
- The iPad is unlocked.
- The iPad trusts this computer.
- OpenDisplay is open in the foreground.
- usbmuxd is running.
- `idevice_id -l` lists the iPad.
- No other OpenDisplay sender is already holding the app connection.

Then run:

~~~sh
tuxdisplay usb status
systemctl status usbmuxd
idevice_id -l
tuxdisplay restart
~~~

Direct USB does not create an IP address. Seeing no new network interface is normal. Personal Hotspot is not required.

If `idevice_id -l` shows nothing, reconnect the cable, unlock the iPad, respond to the trust prompt, and try another known data cable or port.

## Android cable detected, but OpenDisplay does not connect

Android uses ADB as its trusted offline cable transport. It does not require Wi-Fi, mobile data, tethering, or a network address.

Check each item:

- Android 8 or newer is running the current [OpenDisplay Android APK](https://github.com/josepacelli/opendisplay-android/releases/latest). Android 12–13 requires receiver version 0.0.8 or newer.
- **Developer options → USB debugging** is enabled.
- The cable supports data and Android is unlocked.
- The **Allow USB debugging** prompt was accepted for this computer.
- OpenDisplay Android is open and waiting for the sender.
- No other sender is already using the receiver.

Then run:

~~~sh
adb devices -l
tuxdisplay usb status
tuxdisplay restart
~~~

The ADB state must be `device`. If it is `unauthorized`, unlock Android, disconnect and reconnect the cable, then approve the fingerprint prompt. If it is `offline`, restart ADB with `adb kill-server`, reconnect the cable, and try again. If no row appears, select a data-capable USB mode on Android and try another cable or port.

After closing TuxDisplay, `adb forward --list` should not contain a TuxDisplay forwarding entry. TuxDisplay removes its dynamically allocated forward after disconnect or failure.

## AVNC does not connect over the Android cable

Install [AVNC from F-Droid](https://f-droid.org/packages/com.gaurav.avnc/), start TuxDisplay, and configure AVNC with host `127.0.0.1` and port `5900`. Leave authentication empty in GNOME Wayland mode. The address is Android's own loopback interface; TuxDisplay carries it to the laptop through `adb reverse`, so no Wi-Fi address should be entered.

Check:

~~~sh
adb devices -l
adb reverse --list
tuxdisplay status
journalctl --user -u tuxdisplay.service --since "5 minutes ago"
~~~

The device state must be `device`, and the reverse list should contain `tcp:5900 tcp:5900` for its serial. If the entry is absent, unlock Android, approve USB debugging, choose **Connect tablet**, and restart TuxDisplay. If another application already owns Android port 5900, set a different `VNC_PORT` in `~/.config/tuxdisplay/config`, restart TuxDisplay, and use the same port in AVNC.

If AVNC connects but remains black, confirm `tuxdisplay status` reports `AVNC USB: connected` and move a window on the selected monitor. The JPEG branch starts only after the RFB handshake and is damage-driven. Disconnect and reconnect AVNC after a TuxDisplay resolution change.

AVNC is a compatibility path. At high resolutions its JPEG conversion may use more CPU and run below OpenDisplay's hardware-H.264 frame rate. Tight/JPEG limits each encoded rectangle to 2048 pixels wide, so use `2048x1536` or a smaller preset; `2160x1620` is OpenDisplay-only. Start with 1280×800 for a 16:10 Android tablet or 1024×768 for diagnosis. Use OpenDisplay when smooth motion and power efficiency are more important than installing from F-Droid.

In the isolated X11 fallback, AVNC connects to the same address and port but must use the six-digit TuxDisplay PIN as its VNC password.

## “USB gadget unavailable” on a laptop

This message normally means the computer has no USB Device Controller in `/sys/class/udc`. Most x86 laptop ports are host-only. Do not enable the gadget service; use direct OpenDisplay USB instead.

The gadget exists only to give Safari/noVNC a private `10.55.0.1` cable network. It is unrelated to direct OpenDisplay streaming.

## The browser page does not load

1. Run `tuxdisplay url` and use the complete URL including `http://` and port `6080`.
2. Confirm the iPad and computer share the same trusted LAN or supported USB network.
3. Test that the Linux firewall permits TCP 6080 on that private interface.
4. Confirm the service is listening and the URL uses a current host address.
5. Do not use the direct OpenDisplay workflow's lack of IP address as a browser URL.

The `.local` name depends on mDNS/Avahi. If it does not resolve, use the numeric private address printed by `tuxdisplay url`.

## The PIN field does not accept typing

Use the on-screen number keypad in the TuxDisplay login page. On iPad, Safari can withhold the software keyboard from nonstandard or fullscreen contexts. Exit fullscreen, tap the PIN field, and reload the page if the keypad is not visible.

Regenerate a forgotten PIN with:

~~~sh
tuxdisplay password --reset
~~~

Restarting the service invalidates the current authenticated browser session.

## Browser fullscreen appears to do nothing

iPadOS restricts the standard Fullscreen API in some Safari versions and browsing contexts. Try:

1. TuxDisplay's in-page fullscreen/immersive control.
2. Hiding Safari's toolbar.
3. Adding the page to the Home Screen and opening it there.

Fullscreen changes page presentation, not the virtual monitor mode. A mismatched aspect ratio still produces borders.

## Touch works like a mouse

That is intentional. TuxDisplay maps OpenDisplay touch and Pencil to a guarded single pointer so GNOME cannot receive invalid slot sequences. Tap, drag, and scroll are supported. Multi-finger gestures, pressure, tilt, and simultaneous touches are not.

The browser fallback has its own web input path, but browser and iPadOS behavior varies.

## Only an isolated desktop appears

Run `tuxdisplay status` and check the display mode. A real extension requires GNOME on Wayland and the required Mutter APIs. Xorg and other Wayland compositors use the isolated Xvfb/noVNC workspace.

Also check whether `TUXDISPLAY_FORCE_X11=1` was set in the user-service environment.

## The service will not start

~~~sh
tuxdisplay doctor
systemctl --user status tuxdisplay.service
journalctl --user -u tuxdisplay.service -b
~~~

Common causes are missing GStreamer plugins, no PipeWire stream, a stale or unsupported GNOME session, an invalid port already in use, or manual configuration outside the accepted resolution and port ranges. TuxDisplay falls back to safe defaults for invalid configuration, but the log records the selected values.

## Collecting a useful issue report

Include:

- TuxDisplay version and installation source;
- Linux distribution and version;
- desktop and session type from `echo "$XDG_CURRENT_DESKTOP / $XDG_SESSION_TYPE"`;
- tablet model, OS version, receiver application and version;
- selected display mode, resolution, frame rate, and acceleration setting;
- whether the tray is gray, amber, or green;
- output from `tuxdisplay status`, `tuxdisplay usb status`, and `tuxdisplay doctor`;
- sender and receiver health after at least ten seconds of active motion, including drops and recoveries;
- the relevant service log around the failure;
- exact reproduction steps.

Remove the PIN, device identifiers, addresses, and unrelated log content before posting publicly.
