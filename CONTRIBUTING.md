# Contributing

TuxDisplay combines desktop-compositor APIs, PipeWire/GStreamer media, USB transport, browser input, and Debian packaging. Changes should preserve a safe offline USB path and must not make the desktop compositor less stable.

## Development target

The primary supported environment is:

- Debian or Ubuntu;
- GNOME on Wayland;
- PipeWire and the GStreamer plugin set declared in `packaging/DEBIAN/control`;
- an iPad running OpenDisplay;
- usbmuxd and libimobiledevice for direct USB testing.

The X11/noVNC backend should continue to start on sessions without the required Mutter virtual-monitor APIs.

## Repository layout

| Path | Purpose |
| --- | --- |
| `packaging/usr/bin/tuxdisplay` | CLI, GTK manager, tray, and configuration |
| `packaging/usr/lib/tuxdisplay/tuxdisplay-wayland` | GNOME virtual monitor, capture, browser service, and input |
| `packaging/usr/lib/tuxdisplay/opendisplay_usb.py` | OpenDisplay protocol and usbmuxd transport |
| `packaging/usr/lib/tuxdisplay/tuxdisplay-session` | X11 fallback session |
| `packaging/usr/sbin/tuxdisplay-usb` | Optional privileged gadget helper |
| `packaging/usr/share/tuxdisplay/` | Browser and fallback desktop assets |
| `packaging/man/` | Installed manual pages |
| `tests/` | Dependency-free protocol and CLI regression tests |
| `docs/` | Architecture, operations, security, and market context |

## Before submitting a change

~~~sh
python3 -m unittest discover -s tests -v
python3 -m py_compile \
  packaging/usr/bin/tuxdisplay \
  packaging/usr/lib/tuxdisplay/opendisplay_usb.py \
  packaging/usr/lib/tuxdisplay/tuxdisplay-wayland
git diff --check
~~~

For a package candidate:

~~~sh
./build-deb.sh
dpkg-deb --info dist/tuxdisplay_0.4.3_all.deb
dpkg-deb --contents dist/tuxdisplay_0.4.3_all.deb
~~~

The build replaces the package for the current version and regenerates `dist/SHA256SUMS`. Do not commit a rebuilt binary unless the change is intended for a release asset.

## Manual test checklist

For GNOME Wayland changes:

1. Start TuxDisplay and confirm `Meta-0` appears as an extended monitor.
2. Open OpenDisplay before and after connecting the cable.
3. Confirm the first image appears when the virtual desktop is completely static.
4. Test disconnect and reconnect without restarting the service.
5. Test tap, drag, scroll, duplicate begin/end events, and disconnect during a drag.
6. Change between a 16:9 and 4:3 preset and verify recovery.
7. Stop TuxDisplay and confirm the virtual output is removed without affecting GNOME.
8. Test browser PIN entry, MJPEG video, input, and session invalidation.

For fallback changes:

1. Force `TUXDISPLAY_FORCE_X11=1`.
2. Confirm noVNC loads after PIN authentication.
3. Launch an application with `tuxdisplay launch`.
4. Stop the service and confirm Xvfb, x11vnc, websockify, Openbox, and tint2 exit.

Run `tuxdisplay doctor` in both modes.

## Compositor-safety rule

Never forward untrusted receiver events directly into compositor APIs without validating their sequence, range, and lifecycle. In particular:

- clamp coordinates and scroll values;
- balance button or touch down/up state;
- release active state on disconnect;
- do not invent native touch slots when the wire protocol has no slot identity;
- keep a regression test for every crash fix.

Version 0.4.0 demonstrated that malformed touch-slot state can abort Mutter, taking the complete Wayland session with it.

## Documentation

Update documentation in the same change when behavior, commands, dependencies, configuration, transport, security, or compatibility changes:

- keep the README task-oriented;
- keep both manual pages accurate for installed users;
- describe implementation changes in `docs/ARCHITECTURE.md`;
- add operational failure modes to `docs/TROUBLESHOOTING.md`;
- update `docs/SECURITY.md` for a changed trust boundary;
- date and source material changes in `docs/COMPETITIVE_ANALYSIS.md`.

## Release checklist

1. Choose a semantic version and update all embedded version strings.
2. Add a Debian changelog entry with user-visible changes.
3. Update release-specific README commands.
4. Run automated and manual checks.
5. Build the `.deb` and inspect its contents and control scripts.
6. Verify a clean install and upgrade from the previous release.
7. Regenerate and verify `dist/SHA256SUMS`.
8. Tag the exact commit used to build the release.
9. Upload the package and checksum file to the matching GitHub release.
10. Re-check the published warning and compatibility notes.

Do not rewrite historical changelog entries or move an existing tag.
