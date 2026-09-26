# Security

TuxDisplay controls a display capture and accepts remote input. Treat it like a local remote-desktop service even when the receiver is physically beside the computer.

## Trust boundaries

### Direct OpenDisplay USB

The preferred connection travels through either usbmuxd to a paired iPad or a loopback-only ADB port forward to an Android device that has authorized the computer for USB debugging. This avoids LAN exposure and works offline, but OpenDisplay protocol version 3 does not add encryption, authentication, or per-session pairing of its own.

Use direct USB only with:

- a computer and tablet you control;
- a cable and USB path you trust;
- an iPad pairing relationship or Android USB-debugging authorization you recognize.

Lock or disconnect the tablet, revoke its trust/USB-debugging authorization, or stop TuxDisplay when the display is unattended. Android's general USB-debugging authorization grants more than display access to the computer's ADB client, so enable it only for computers you trust and revoke it in Developer options when it is no longer needed.

TuxDisplay passes the selected Android serial as a direct process argument, allocates a host port through ADB, binds the forwarding side to loopback, and removes that forward on disconnect. It does not invoke an Android shell command or install the receiver APK.

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

The in-app updater applies the same policy before it requests system authentication. It accepts only a newer stable semantic version from the repository's latest-release API, requires the exact versioned `.deb` and `SHA256SUMS` assets, restricts metadata and downloads to HTTPS GitHub hosts, enforces response-size limits, verifies the published SHA-256 and any asset digest returned by GitHub, and checks the package name, version, and `all` architecture with `dpkg-deb`. The user must explicitly choose installation and approve the PolicyKit prompt; installation is delegated to `apt-get`.

These checks protect against accidental corruption, unsafe redirects, and asset mix-ups. They do not protect against compromise of the GitHub repository or release account because the package and checksum share that trust root. The updater does not send the display stream, configuration, PIN, or tablet identifier to GitHub.

## Hardening recommendations

- Prefer direct USB over the browser fallback.
- Keep TuxDisplay, the selected OpenDisplay receiver, the tablet OS, GNOME, GStreamer, usbmuxd/libimobiledevice, and ADB updated.
- Bind or firewall the browser port to trusted interfaces when using a persistent setup.
- Use `tuxdisplay password --reset` after temporary browser sharing.
- Do not run the display service as root.
- Leave `tuxdisplay-usb-gadget.service` disabled unless gadget networking is explicitly required.
- Review `journalctl --user -u tuxdisplay.service` after unexplained connections.
- Inspect the version and release notes shown by the updater before approving installation.

## Known limitations

- OpenDisplay v3 provides no application-layer encryption or authentication.
- Browser access is HTTP rather than HTTPS.
- The six-digit browser PIN has a small brute-force space.
- There is no persistent per-device allowlist above iPadOS pairing or Android ADB authorization.
- The project does not yet publish signed or reproducible release attestations.

Report security-sensitive issues privately to the repository owner rather than opening a public issue containing exploit details or secrets. The project does not currently publish a dedicated security-response SLA.
