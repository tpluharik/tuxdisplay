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

TuxDisplay 0.4.0 could send invalid native touch state to Mutter and abort GNOME Shell. TuxDisplay 0.4.3 could reject GNOME's negotiated PipeWire rate, while 0.4.4 could periodically reconnect a healthy low-FPS stream. Upgrade to 0.4.9 or newer:

~~~sh
sudo apt install ./tuxdisplay_0.4.9_all.deb
tuxdisplay restart
~~~

Version 0.4.1 introduced guarded pointer translation. Version 0.4.2 added cached-keyframe recovery for static first frames. Version 0.4.3 added fresh-IDR gating, receiver-health recovery, and bounded shutdown. Version 0.4.4 accepts GNOME's negotiated PipeWire rate. Version 0.4.5 prevents false watchdog reconnects on quiet or low-FPS desktops. Version 0.4.6 adds optional closed-lid operation. Version 0.4.7 unifies the desktop application and adds verified in-app updates. Version 0.4.8 adds Android OpenDisplay over an ADB USB tunnel. Version 0.4.9 remembers monitor placement and refreshes capture after a GNOME display-layout change.

## OpenDisplay shows a black screen

1. Confirm `tuxdisplay status` reports GNOME Wayland mode and a running service.
2. Confirm the package version is at least 0.4.8 when using Android.
3. Move the pointer or a window onto `Meta-0` to create screen damage.
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

Version 0.4.9 listens for GNOME monitor-topology changes and refreshes the existing PipeWire and OpenDisplay stream in place. It also saves `Meta-0` relative to the nearest physical monitor, so a new virtual-monitor identity can return to the same side and offset after restart. Upgrade if rearranging screens leaves the tablet on its previous frame.

On 0.4.9 or newer, wait about one second after pressing **Apply** in GNOME Displays. The log should contain `monitor arrangement changed; refreshing the video stream`. If the image remains frozen, run `tuxdisplay restart` and include the service log in a bug report.

## The image pauses after changing TuxDisplay resolution

A resolution change restarts the virtual monitor and the video session. During that transition the tablet can continue displaying its last decoded frame.

1. Wait a few seconds for the amber tray state to return.
2. Reopen OpenDisplay if it did not reconnect.
3. If necessary, choose **Close connection**, start TuxDisplay again, and reconnect.
4. Look on the laptop display for applications GNOME moved away from the removed virtual output. TuxDisplay will restore the saved monitor placement when `Meta-0` returns.

This is a lifecycle limitation, not a tablet network problem. Dynamic in-place mode switching is not implemented.

## The image does not fill the tablet

The default 1920×1080 mode is 16:9. Most traditional iPads are closer to 4:3, so select 2048×1536 or 2160×1620. Many Android tablets are closer to 16:10, so try 1280×800. Use 1024×768 if performance matters more than detail.

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

- Android 8 or newer is running the current [OpenDisplay Android APK](https://github.com/josepacelli/opendisplay-android/releases/latest).
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
- tablet model, OS version, OpenDisplay receiver and version;
- selected resolution;
- whether the tray is gray, amber, or green;
- output from `tuxdisplay status`, `tuxdisplay usb status`, and `tuxdisplay doctor`;
- the relevant service log around the failure;
- exact reproduction steps.

Remove the PIN, device identifiers, addresses, and unrelated log content before posting publicly.
