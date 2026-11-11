# Troubleshooting

Start with:

~~~sh
tuxdisplay status
tuxdisplay usb status
tuxdisplay doctor
systemctl --user status tuxdisplay.service
journalctl --user -u tuxdisplay.service --since "10 minutes ago"
~~~

The first three commands are safe to paste into a bug report only after review. Remove usernames, hostnames, IP addresses, tablet identifiers, and browser/AVNC session passwords.

## Do not run 0.4.0 on GNOME Wayland

TuxDisplay 0.4.0 could send invalid native touch state to Mutter and abort GNOME Shell. Older releases also had display-refresh and restart-loop failures. Upgrade to 0.4.26 or newer for the current stability, active-motion pacing, and hardened compatibility/update paths:

~~~sh
sudo apt install ./tuxdisplay_0.4.26_all.deb
tuxdisplay restart
~~~

Version 0.4.1 introduced guarded pointer translation. Versions 0.4.2–0.4.17 added cached-keyframe, receiver-health, layout-refresh, and bounded pipeline recovery. Versions 0.4.18–0.4.20 separated cursor work from video and added detailed performance telemetry. Version 0.4.21 added AVNC, 0.4.23 added safe lid-close cleanup, and 0.4.24 added guarded native single-finger touch. Version 0.4.25 hardened the opt-in compatibility and updater paths. Version 0.4.26 restores smooth configured-rate output during activity while returning the video path to idle after 500 ms of quiet.

## Motion on the tablet is jumpy

Open the manager and leave **Video acceleration** on **Automatic (hardware preferred)**. Then run `tuxdisplay status` while moving a window or scrolling on the tablet. `PipeWire source` and `Pipeline input` count distinct compositor updates, `Encoded video` counts the adaptive paced output, `source_fps` is H.264 entering the USB sender, `sent_fps` is the rate written to the cable, and the receiver line is OpenDisplay's own non-normative telemetry.

At a configured 30 FPS, encoded, cable, and receiver values around 29–30 FPS during sustained motion are normal because the sender and receiver sample over independent time windows. PipeWire may report fewer distinct damage frames; TuxDisplay repeats the newest one only during the active window so the tablet renderer remains regularly clocked. After 500 ms without changed pixels or input, rates intentionally fall to zero and `frame_pacing=adaptive-idle` confirms this is not a freeze. A healthy session normally has `queued` near zero and keeps `drops=0` and `recoveries=0`.

Version 0.4.26 defaults new configurations to **Smooth OpenDisplay overlay**. It should show `Cursor transport: mode=xwayland-poll`; its update count should rise while the pointer moves over the tablet without forcing full-frame encoding. If it reports `pipewire-metadata`, XWayland cursor polling was unavailable. If the pointer is missing because the receiver ignores OpenDisplay cursor messages, select **Visible in video (compatibility)** or run `tuxdisplay configure --cursor-mode embedded --restart`. For smoother full-window motion on a 4:3 iPad, select `1536x1152` in the manager or run `tuxdisplay configure --resolution 1536x1152 --restart`.

If receiver health changes to `stale=True`, TuxDisplay has stopped trusting the displayed receiver counters. It first sends a cached frame and requests a fresh IDR. If a valid report does not return within roughly seven more seconds, the USB session reconnects automatically; manually restarting the whole display service should no longer be necessary.

If sender and receiver health both stop updating, version 0.4.17 treats the encoded-frame callback as stalled after eight seconds and recycles the service. When this happens on the hardware encoder, the restarted service uses software encoding for 24 hours. If diagnostics show `recovery=suppressed`, two automatic pipeline recoveries already occurred in ten minutes; TuxDisplay leaves the service stable instead of entering a restart loop. Stop it, collect the service log, and investigate PipeWire or the graphics driver before retrying.

- If `drops=0`, `recoveries=0`, and sender and receiver rates agree during motion, the USB transport is healthy.
- If `encoded_fps` is low during continuous motion while `frame_pacing=adaptive-active`, select 30 FPS or a smaller resolution such as 1024×768.
- If `source_fps` is healthy but `sent_fps` is lower or recoveries rise, reconnect with another data-capable cable or USB port.
- If automatic acceleration falls back to software, confirm the VA-API GStreamer elements are installed and usable; `tuxdisplay doctor` and the service log identify the active encoder.

The 60 FPS option is deliberately not the default. At 2048×1536 it requires roughly twice the active encode work and bitrate of 30 FPS; use it only when live sender telemetry remains stable. If the manager says 60 FPS but `encoded_fps` and `source_fps` remain much lower during sustained motion, the host encoder cannot maintain that preset. Use 30 FPS or reduce the resolution rather than accepting inconsistent motion.

## OpenDisplay shows a black screen

1. Confirm `tuxdisplay status` reports GNOME Wayland mode and a running service.
2. Confirm the package version is at least 0.4.8 when using Android.
3. Check that pipeline and sender telemetry appear after the receiver connects. On 0.4.26 or newer, a static desktop reports `frame_pacing=adaptive-idle`; move a window to reopen the active video path.
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

This is the safe default in version 0.4.23 and newer. TuxDisplay disconnects the receiver, removes the virtual monitor in Extend mode, and stops before the laptop sleeps. Open the lid and choose **Start display** to reconnect.

Enable **Keep awake with lid closed** only when the tablet must remain active with the lid shut. The manager restarts the display once so the service can acquire its blocking logind inhibitor. Confirm it with `tuxdisplay status`; the output should say that the connection stays active and system sleep is blocked while TuxDisplay runs.

The blocking inhibitor is released when TuxDisplay stops. It intentionally blocks manual and idle suspend as well as lid-triggered sleep, but firmware thermal protection and critical-battery handling may still shut down or suspend the computer. Keep a closed laptop ventilated.

If the default automatic disconnection does not occur, run `tuxdisplay status`, check `/proc/acpi/button/lid/*/state`, and inspect the user-service journal. Systems without an ACPI lid file still use UPower and logind sleep notifications.

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

Install [AVNC from F-Droid](https://f-droid.org/packages/com.gaurav.avnc/), connect and authorize the tablet, then select that exact device under **AVNC compatibility** in TuxDisplay and restart. Configure AVNC with host `127.0.0.1`, port `5900`, no username, and the fresh **AVNC session password** shown by TuxDisplay. No Wi-Fi address should be entered.

Check:

~~~sh
adb devices -l
adb reverse --list
tuxdisplay status
journalctl --user -u tuxdisplay.service --since "5 minutes ago"
~~~

The selected device state must be `device`, and the reverse list should contain `tcp:5900 tcp:5900` only for that serial. If absent, unlock Android, approve USB debugging, reselect the device, and restart TuxDisplay. If another application owns Android port 5900, set a different `VNC_PORT`, restart, and use the same port in AVNC.

If AVNC connects but remains black, confirm `tuxdisplay status` reports `AVNC USB: connected` and move a window on the selected monitor. The JPEG branch starts only after the RFB handshake and follows adaptive active/idle pacing. Disconnect and reconnect AVNC after a TuxDisplay resolution change.

AVNC is a compatibility path. At high resolutions its JPEG conversion may use more CPU and run below OpenDisplay's hardware-H.264 frame rate. Tight/JPEG limits each encoded rectangle to 2048 pixels wide, so use `2048x1536` or a smaller preset; `2160x1620` is OpenDisplay-only. Start with 1280×800 for a 16:10 Android tablet or 1024×768 for diagnosis. Use OpenDisplay when smooth motion and power efficiency are more important than installing from F-Droid.

After five failed passwords in one minute, wait five minutes or restart the display to create a new AVNC session. Only one AVNC client can be connected at a time.

## “USB gadget unavailable” on a laptop

This message normally means the computer has no USB Device Controller in `/sys/class/udc`. Most x86 laptop ports are host-only. Do not enable the gadget service; use direct OpenDisplay USB instead.

The gadget exists only to give Safari/noVNC a private `10.55.0.1` cable network. It is unrelated to direct OpenDisplay streaming.

## The browser page does not load

1. Enable **Browser fallback** in the manager and restart the display.
2. Run `tuxdisplay url` and use the complete URL including `http://` and port `6080`.
3. Confirm the URL is loopback for local preview or an address on an active USB network; LAN and Wi-Fi listeners are intentionally unsupported.
4. Confirm the service is listening and the URL uses the current USB address.
5. Do not use the direct OpenDisplay workflow's lack of IP address as a browser URL.

## The PIN field does not accept typing

Use the on-screen number keypad in the TuxDisplay login page. On iPad, Safari can withhold the software keyboard from nonstandard or fullscreen contexts. Exit fullscreen, tap the PIN field, and reload the page if the keypad is not visible.

Regenerate a forgotten PIN with:

~~~sh
tuxdisplay password --reset
~~~

Restarting the service invalidates the current authenticated browser session and rotates the PIN. The manager shows the new value.

## Browser fullscreen appears to do nothing

iPadOS restricts the standard Fullscreen API in some Safari versions and browsing contexts. Try:

1. TuxDisplay's in-page fullscreen/immersive control.
2. Hiding Safari's toolbar.
3. Adding the page to the Home Screen and opening it there.

Fullscreen changes page presentation, not the virtual monitor mode. A mismatched aspect ratio still produces borders.

## Finger touch, scrolling, and zoom

Version 0.4.24 maps OpenDisplay finger events to one guarded native GNOME touch contact. A one-finger swipe therefore scrolls or directly manipulates content in touch-aware applications instead of acting as a held mouse button. Duplicate or orphaned phases are suppressed, and an active contact is released when the cable disconnects. Apple Pencil deliberately remains a pointer, while AVNC keeps the input mode selected inside AVNC.

OpenDisplay's separate two-finger scroll message remains a normal bounded scroll-axis event. True pinch zoom is not available through OpenDisplay protocol v3 because the receiver sends neither stable identities for multiple contacts nor a magnification value. Application-specific zoom buttons and keyboard shortcuts still work; adding native pinch requires a compatible receiver protocol extension rather than guessing touch state in Mutter.

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
