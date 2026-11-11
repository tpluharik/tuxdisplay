# Contributing

TuxDisplay combines desktop-compositor APIs, PipeWire/GStreamer media, USB transport, browser input, and Debian packaging. Changes should preserve a safe offline USB path and must not make the desktop compositor less stable.

## Development target

The primary supported environment is:

- Debian or Ubuntu;
- GNOME on Wayland;
- PipeWire and the GStreamer plugin set declared in `packaging/DEBIAN/control`;
- an iPad running OpenDisplay and/or an Android device running OpenDisplay Android or AVNC;
- usbmuxd/libimobiledevice for iPadOS testing and ADB for Android USB testing.

The X11/noVNC backend should continue to start on sessions without the required Mutter virtual-monitor APIs.

## Repository layout

| Path | Purpose |
| --- | --- |
| `packaging/usr/bin/tuxdisplay` | CLI, GTK manager, tray, and configuration |
| `packaging/usr/lib/tuxdisplay/tuxdisplay-wayland` | GNOME extension/mirroring, capture, browser service, and input |
| `packaging/usr/lib/tuxdisplay/display_source.py` | Primary-monitor selection and mirrored touch mapping |
| `packaging/usr/lib/tuxdisplay/opendisplay_usb.py` | OpenDisplay protocol plus usbmuxd and Android ADB transports |
| `packaging/usr/lib/tuxdisplay/tightvnc_usb.py` | Loopback Tight/JPEG RFB server and Android ADB reverse lifecycle |
| `packaging/usr/lib/tuxdisplay/update_security.py` | Ed25519 manifest, URL, expiry, and package-digest verification |
| `packaging/usr/lib/tuxdisplay/update-helper` | Fixed PolicyKit root helper and root-owned update staging |
| `packaging/usr/lib/tuxdisplay/video_pipeline.py` | Bounded GStreamer graphs, pacing, and encoder selection |
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
  packaging/usr/lib/tuxdisplay/display_source.py \
  packaging/usr/lib/tuxdisplay/cursor_tracking.py \
  packaging/usr/lib/tuxdisplay/opendisplay_usb.py \
  packaging/usr/lib/tuxdisplay/tightvnc_usb.py \
  packaging/usr/lib/tuxdisplay/video_pipeline.py \
  packaging/usr/lib/tuxdisplay/tuxdisplay-wayland
git diff --check
~~~

For a package candidate:

~~~sh
./build-deb.sh
dpkg-deb --info dist/tuxdisplay_0.4.26_all.deb
dpkg-deb --contents dist/tuxdisplay_0.4.26_all.deb
~~~

The build replaces the package for the current version, normalizes the complete staging tree, and regenerates `dist/SHA256SUMS`. Keep `SOURCE_DATE_EPOCH` equal to the newest Debian changelog timestamp. Build products are ignored and belong in GitHub Releases, never source control.

## Manual test checklist

For GNOME Wayland changes:

1. In Extend mode, start TuxDisplay and confirm `Meta-0` appears as an extended monitor.
2. Open OpenDisplay before and after connecting the cable.
3. Confirm the first image appears when the virtual desktop is completely static.
4. Test disconnect and reconnect without restarting the service.
5. Test native finger taps and one-finger content scrolling, duplicate and orphaned touch phases, and disconnect during an active contact. Confirm Pencil still behaves as a pointer and explicit two-finger scroll remains an axis event.
6. Change between a 16:9 and 4:3 preset and verify recovery.
7. Stop TuxDisplay and confirm the virtual output is removed without affecting GNOME.
8. Confirm the browser is off by default. Enable it, verify only loopback/USB listeners, test PIN throttling, MJPEG/input, then confirm restart rotates the PIN and cookie.
9. Confirm app-grid activation reuses the background tray process and shows the TuxDisplay icon.
10. Exercise update checking with valid, expired, malformed, wrong-key, and digest-mismatched manifests; verify the root helper independently re-downloads and rejects every mismatch.
11. On Android, test unauthorized and authorized ADB states, receiver launch after service start, cable reconnect, and cleanup with `adb forward --list`.
12. In Mirror mode, verify the current primary physical monitor is captured, no `Meta-0` is created, and tap/drag/scroll land correctly with both matching and mismatched aspect ratios.
13. At 15, 30, and 60 FPS, compare distinct PipeWire rate, paced encode rate, `source_fps`, `sent_fps`, and receiver FPS after at least ten seconds of sustained motion. Confirm 0.4.26+ reaches the selected cadence during motion, enters `adaptive-idle` after quiet content, and keeps `drops` and `recoveries` at zero in the supported baseline.
14. After the receiver has reported health, stop only its statistics while leaving control traffic and active video running. Confirm the data is marked stale and a keyframe is requested near eight seconds, then the receiver reconnects near fifteen seconds. Confirm a receiver that never sends statistics and a connected receiver during intentional video idle are not disconnected by this watchdog.
15. Stop the encoded-frame callback and receiver statistics together. Confirm 0.4.17+ requests one service recycle near eight seconds, records a 24-hour software fallback after a hardware stall, and suppresses a third automatic recycle within ten minutes.
16. Exercise both automatic and software encoding. If VA-API is available, confirm Automatic selects it; if initialization fails, confirm the service falls back once to x264 without a restart loop.
17. Move the pointer across the tablet without changing desktop content. Confirm `Cursor transport` reports `xwayland-poll`, its update count rises smoothly, and capture/source rates remain near the quiet-screen cadence.
18. Confirm AVNC is off by default. Select exactly one authorized device, use the fresh session password at Android `127.0.0.1:5900`, reject a second client, test throttling, and confirm no mapping is created for another authorized tablet.
19. With **Keep awake with lid closed** disabled, close the lid on a safe test machine and confirm the receiver disconnects, the user service stops, and `Meta-0` is removed before sleep. Reopen the lid and confirm TuxDisplay remains stopped. Enable the option and confirm the service instead remains active while lid sleep is inhibited.

For fallback changes:

1. Force `TUXDISPLAY_FORCE_X11=1`.
2. Confirm noVNC loads after PIN authentication.
3. Launch an application with `tuxdisplay launch`.
4. Stop the service and confirm Xvfb, x11vnc, websockify, Openbox, and tint2 exit.
5. Select one AVNC device, connect with the fresh password, then confirm the helper and mapping exit with the service.

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
4. Validate the AppStream metadata, desktop launchers, shell syntax, Python compilation, manual-page rendering, and Markdown links.
5. Run automated and manual checks, including a real OpenDisplay receiver when transport or video behavior changed.
6. Build the `.deb` and inspect its contents and control scripts.
7. Verify a clean install and upgrade from the previous release.
8. Regenerate and verify `dist/SHA256SUMS` from inside `dist/`.
9. Use `scripts/sign-update-manifest.py` with the offline Ed25519 private key and commit only `update/latest.json`; never copy the private key into the repository or package.
10. Verify a second clean build matches the manifest digest byte-for-byte.
11. Tag the exact commit used to build the release. The tag workflow verifies the manifest and requests artifact provenance.
12. Upload the package and checksum file to the matching GitHub release.
13. Download the published assets again, verify the checksum and signed manifest, and confirm the updater can parse the release.
14. Re-check the published warning, compatibility notes, asset list, workflow result, and remote tag commit.

Do not rewrite historical changelog entries or move an existing tag.
