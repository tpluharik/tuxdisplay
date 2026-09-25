# Security

TuxDisplay controls a display capture and accepts remote input. Treat it like a local remote-desktop service even when the receiver is physically beside the computer.

## Trust boundaries

### Direct OpenDisplay USB

The preferred connection travels through usbmuxd between a computer and an iPad that has trusted that computer. This avoids LAN exposure and works offline, but OpenDisplay protocol version 3 does not add encryption, authentication, or per-session pairing of its own.

Use direct USB only with:

- a computer and iPad you control;
- a cable and USB path you trust;
- an iPad pairing relationship you recognize.

Lock or disconnect the iPad, revoke the trust relationship, or stop TuxDisplay when the display is unattended.

### Browser fallback

The browser service listens on local interfaces so it can be reached from a LAN or USB network. It uses a generated six-digit PIN and an HTTP-only, same-site session cookie. Video, credentials, and input still travel over ordinary HTTP.

Consequences:

- use only a trusted private LAN or private cable network;
- do not port-forward or expose TCP 6080 to the Internet;
- do not use an untrusted public Wi-Fi network;
- reset the PIN if it was observed or shared;
- stop TuxDisplay when browser access is no longer needed.

The PIN reduces accidental access; six digits are not a substitute for encrypted transport or a strong account credential.

### Privileged USB gadget helper

The optional `tuxdisplay-usb` helper changes ConfigFS USB gadget state, creates a network interface, assigns `10.55.0.1/24`, and runs a private dnsmasq process. It requires root through a narrowly scoped PolicyKit action or system service.

Only enable the system service on hardware with an intended device/dual-role USB port. Direct OpenDisplay USB does not require this helper or root access.

## Local files

Per-user configuration and authentication files are created with mode `0600`:

- `~/.config/tuxdisplay/config`
- `~/.config/tuxdisplay/password`
- `~/.config/tuxdisplay/*.rfb` when the VNC fallback is used

Runtime state lives below `~/.local/state/tuxdisplay/`. Logs can contain local addresses, device status, application errors, and filenames. Review and redact them before sharing.

The Debian package installs system files as root-owned, while the display service runs as the logged-in desktop user.

## Input implications

An attached receiver can move the pointer, click, scroll, and—in the browser path—send keyboard input. This can interact with applications under the desktop user's authority. GNOME's own permission and session boundaries still apply, but TuxDisplay should not be left connected to an untrusted receiver.

OpenDisplay input is reduced to a guarded single-pointer stream. This protects compositor stability; it is not an authorization mechanism.

## Release integrity

Release assets include `SHA256SUMS`. Download the package and checksum file from the same tagged GitHub release and verify the package before installation:

~~~sh
sha256sum --ignore-missing --check SHA256SUMS
~~~

SHA-256 detects a damaged or substituted file relative to the published checksum. Releases are not currently documented as reproducible or cryptographically signed, so verify the GitHub repository and release source as well.

## Hardening recommendations

- Prefer direct USB over the browser fallback.
- Keep TuxDisplay, OpenDisplay, iPadOS, GNOME, GStreamer, usbmuxd, and libimobiledevice updated.
- Bind or firewall the browser port to trusted interfaces when using a persistent setup.
- Use `tuxdisplay password --reset` after temporary browser sharing.
- Do not run the display service as root.
- Leave `tuxdisplay-usb-gadget.service` disabled unless gadget networking is explicitly required.
- Review `journalctl --user -u tuxdisplay.service` after unexplained connections.

## Known limitations

- OpenDisplay v3 provides no application-layer encryption or authentication.
- Browser access is HTTP rather than HTTPS.
- The six-digit browser PIN has a small brute-force space.
- There is no persistent per-iPad allowlist above the operating system's pairing controls.
- The project does not yet publish signed or reproducible release attestations.

Report security-sensitive issues privately to the repository owner rather than opening a public issue containing exploit details or secrets. The project does not currently publish a dedicated security-response SLA.
