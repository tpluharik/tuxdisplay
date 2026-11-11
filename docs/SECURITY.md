# Security

TuxDisplay captures a desktop and can inject input. Treat every receiver path as remote-desktop access even when the tablet is beside the computer.

## Secure defaults in 0.4.27

- Direct OpenDisplay remains the default; its H.264 path adaptively paces active motion, idles on a static desktop, and rate-limits capture-only wake recovery.
- Browser fallback is disabled until explicitly enabled.
- AVNC compatibility is disabled until one authorized Android serial is explicitly selected.
- No browser or VNC service listens on a LAN wildcard address.
- Browser and AVNC credentials are generated for each display-service session.
- In-app updates require an independent Ed25519 signature and are installed by a fixed root-owned helper.

Existing configurations are migrated safely: missing `BROWSER_ENABLED` and `AVNC_DEVICE` values resolve to disabled.

## Trust boundaries

### Direct OpenDisplay USB

The preferred path reaches a paired iPad through usbmuxd or one authorized Android device through an ADB port forward. Host sockets stay on loopback and mappings are removed when the connection closes. OpenDisplay protocol version 3 has no additional application-layer encryption or pairing, so the iPad trust record or Android USB-debugging authorization is the trust boundary.

Use only devices, cables, and USB paths you control. Revoke an iPad pairing or Android USB-debugging authorization when it is no longer needed. Android USB debugging permits more than display access, so do not approve an untrusted computer.

### AVNC over Android USB

AVNC is an optional compatibility receiver. The user must select one currently authorized Android serial in the TuxDisplay manager. TuxDisplay then:

1. binds Tight/JPEG VNC only to host `127.0.0.1`;
2. creates `adb -s SERIAL reverse` only for the selected serial;
3. advertises RFB VNC Authentication, never Security Type None;
4. generates a fresh eight-character password for the service session;
5. permits one VNC client at a time;
6. blocks authentication for five minutes after five failures in one minute; and
7. removes the ADB reverse mapping and password when the display stops.

The manager and `tuxdisplay status` show the current AVNC password through per-user files with mode `0600`. VNC Authentication is challenge-response protection, not transport encryption. The ADB cable and authorization still protect confidentiality.

The X11 compatibility backend uses x11vnc with a fresh password file. Password material is supplied through the prompt input stream and is not placed in the process argument list. x11vnc is loopback-only, IPv6-disabled, single-client, and started with its safer remote-control restrictions.

### Browser receiver

Browser fallback is opt-in. On GNOME Wayland, the HTTP server binds separately to `127.0.0.1` and active USB-network IPv4 addresses (`usb*`, ipheth, or the configured USB gadget). It never binds `0.0.0.0`, Wi-Fi, Ethernet, or a Bonjour/LAN wildcard.

Each service start rotates the six-digit PIN and cookie token. Authentication is limited to five failures per source per minute, followed by a five-minute block. Requests must use an expected Host value, and state-changing POST requests must have an exact same-origin `Origin` header. Authenticated cookies are `HttpOnly` and `SameSite=Strict`.

The browser path uses HTTP because it is designed for a direct USB network with no public certificate infrastructure. Do not route that USB interface, proxy the service, or expose it to a LAN or the Internet. The isolated X11 browser listener is loopback-only.

### Local user boundary

Runtime state and credentials are stored under the user's configuration/state directories with directory mode `0700` and file mode `0600`. The AVNC VNC socket remains loopback-only but also requires its session password. Another process running as the same Unix user can generally read that user's desktop and credentials; TuxDisplay does not try to isolate mutually untrusted processes within one Unix account.

## Update trust and privilege boundary

The updater does not trust a checksum fetched from the same unsigned release page as the package. It downloads `update/latest.json`, verifies its Ed25519 signature against a public key embedded in TuxDisplay, checks expiry, exact package name, exact GitHub release URL, semantic version, and SHA-256 digest.

After PolicyKit authentication, `/usr/lib/tuxdisplay/update-helper` independently repeats manifest verification and downloads the package itself. It stages the file with `O_EXCL` and `O_NOFOLLOW` in a root-owned mode-`0700` directory, verifies the signed digest, validates Debian package name/version/architecture, then invokes APT. A user-owned temporary path is never passed to a privileged package manager.

The private Ed25519 release key is not stored in the repository or Debian package. Compromise of that key requires a new package release with a rotated embedded public key. The manifest expires so a captured document cannot authorize updates indefinitely.

## System privilege

The optional USB gadget helper and signed update helper are the only PolicyKit entry points. Both require a fresh administrator authentication (`auth_admin`); authorization is not retained with `auth_admin_keep`. The USB helper accepts only fixed `setup`, `teardown`, and `status` operations and uses the dedicated `10.55.0.1/24` link.

## Build and release integrity

The build fixes `SOURCE_DATE_EPOCH`, normalizes every staged file and directory mtime, uses deterministic gzip for documentation, stores Debian archive members without compressor-version variance, and writes `SHA256SUMS` for only the current package. Historical `.deb` files are release assets, not source-controlled build inputs. CI runs the test suite and builds twice to detect non-reproducible output. The tag workflow verifies the signed manifest/package digest before publishing and requests GitHub artifact provenance.

Release signatures improve the update path but do not prove runtime behavior on every graphics stack. A release is not considered end-user validated until it has also been installed and exercised on the target GNOME/Wayland/receiver combination.

## Input and compositor safety

OpenDisplay version 3 exposes one finger stream without stable multi-touch contact identifiers. TuxDisplay maps it to one guarded Mutter touch slot, suppresses duplicate/orphaned phases, and releases the slot on disconnect. Pencil remains an independent pointer stream. This prevents the invalid touch state that could abort Mutter in version 0.4.0.

AVNC emits standard VNC pointer, wheel, and keyboard events and does not enter Mutter's native touch path.

## Lid close and shutdown

By default, logind sleep and lid-close signals trigger a bounded clean shutdown: USB transports close, ADB mappings are removed, capture stops, and the virtual monitor is removed. **Keep awake with lid closed** is an explicit override and its inhibitor exists only while the service process is alive.

## Reporting a vulnerability

Do not include passwords, pairing records, device identifiers, private update keys, or personal desktop captures in a public issue. Report the affected version, backend, receiver, reproduction steps, and sanitized logs. Use a private GitHub security advisory when the issue enables unauthorized viewing, input, privilege escalation, or update compromise.
