# Competitive analysis

**Snapshot date:** 2026-09-26

TuxDisplay serves a narrow combination that many second-display products do not: a Debian/Ubuntu GNOME Wayland host, an iPadOS or Android receiver, a real extended desktop, and operation through an ordinary USB data cable without Internet access or IP networking.

This is a feature and positioning review based on public first-party documentation. It is not a latency, image-quality, battery, or reliability benchmark. Commercial pricing changes frequently and is intentionally not reproduced here.

## Evaluation criteria

The comparison emphasizes:

1. Linux as the display host.
2. A real extended desktop rather than only mirroring or remote control.
3. iPadOS and Android receiver support.
4. Direct USB operation without Wi-Fi, tethering, or a cable IP network.
5. Wayland integration.
6. Touch/Pencil behavior.
7. Setup burden, accounts, paid software, or additional hardware.

“Conditional extension” means the receiver can show a host-provided extra output, but the product does not create a native extended monitor on every supported Linux desktop by itself.

## Comparison

| Product | Linux host | Real extra desktop | Tablet receiver | Offline cable path | Input | Main trade-off |
| --- | --- | --- | --- | --- | --- | --- |
| **TuxDisplay** | Yes; Debian/Ubuntu, GNOME Wayland focus | Yes on GNOME Wayland; isolated workspace elsewhere | OpenDisplay on iPadOS/Android or a browser | Yes; usbmuxd or Android ADB, no IP | Tap, drag, scroll; Pencil as pointer on iPadOS | GNOME-specific native path; software encoding; no native multi-touch |
| **OpenDisplay Linux sender** | Yes; KDE Plasma Wayland and Hyprland documented | Yes on documented compositors | OpenDisplay | Yes; usbmuxd, plus Wi-Fi | Project-dependent | Closest open-source alternative, but explicitly experimental and not GNOME-focused |
| **Weylus** | Yes, plus macOS and Windows | Conditional; needs a host-created output/region | Any modern browser | Network transport; can use an existing tethered network | Strong stylus, pressure, tilt, and multi-touch support | Broad input support, but not a turnkey native GNOME extra monitor |
| **Deskreen** | Yes, plus macOS and Windows | Conditional; a virtual output or dummy plug supplies a second screen | Any modern browser | Network/WebRTC | Browser interaction model | Very broad receiver compatibility; second-monitor setup is separate |
| **Sunshine + Moonlight** | Yes, plus macOS and Windows | No native extra monitor by itself | Moonlight client | IP network | Game/remote-stream input | Excellent remote/game streaming ecosystem, different primary use case |
| **Apple Sidecar** | No; Mac host only | Yes | Native iPadOS feature | USB or wireless | Touch gestures and Apple Pencil in supported workflows | Deep Apple integration, unavailable to Linux users |
| **Duet Display** | No official Linux desktop host | Yes on supported Mac/Windows hosts | Native iPad app | Wired and wireless modes | Touch and Pencil features vary by plan/platform | Polished commercial product, but no documented Linux host |
| **Luna Display** | No; Mac/Windows hosts | Yes | Native iPad app | Wired/wireless options require Luna hardware | Touch/Pencil features | Dedicated hardware purchase and no Linux support |
| **spacedesk** | No documented Linux primary host | Yes on supported primary hosts | Native iOS viewer or browser | TCP/IP networking | Touch/remote input | Flexible network display, but Linux is not a primary-machine platform |

## Source notes

### OpenDisplay and the Linux sender

The official [OpenDisplay repository](https://github.com/peetzweg/opendisplay) describes an open protocol and a macOS-to-iPad product with USB and Wi-Fi connections. Its [protocol specification](https://github.com/peetzweg/opendisplay/blob/main/PROTOCOL.md) defines H.264 video, control/input messages, and a transport-independent TCP receiver on port 9000. The project lists [OpenDisplay Android](https://github.com/josepacelli/opendisplay-android) as a compatible third-party receiver; that receiver publishes Android 8+ APK releases and documents ADB forwarding for USB use.

TuxDisplay is an independent Linux sender for that public protocol. The separate [opendisplay-linux project](https://github.com/tixwho/opendisplay-linux) documents KDE Plasma Wayland and Hyprland support, USB and Wi-Fi transport, PipeWire/FFmpeg capture, hardware-encoder options, and an experimental Qt interface. Its own README calls the project highly experimental and does not list GNOME as a supported compositor. It is the closest technical alternative and also a useful adjacent implementation, not merely a generic competitor.

### Weylus

[Weylus](https://github.com/H-M-H/Weylus) runs on Linux, macOS, and Windows and uses a browser as the tablet client. Its Linux integration is especially attractive for stylus users because it documents pressure, tilt, and multi-touch through uinput. Wayland support is described as experimental. Creating a distinct workspace depends on the host's Xorg virtual-head, dummy-output, or compositor facilities, so its default screen-sharing capability should not be mistaken for automatic native monitor creation.

### Deskreen

[Deskreen](https://github.com/pavlobu/deskreen) turns any device with a web browser into a secondary screen and uses WebRTC. Its documentation distinguishes screen/application sharing from using a virtual display adapter or dummy plug for a true additional screen. It has excellent receiver reach but depends on IP networking and leaves native display creation to the host environment.

### Sunshine and Moonlight

[Sunshine](https://docs.lizardbyte.dev/projects/sunshine/latest/) is a self-hosted stream host for Moonlight clients on Linux, macOS, and Windows. It is optimized around low-latency desktop/game streaming over a network. It can stream an existing display or application, but a separate virtual-monitor solution is still needed if the goal is a new desktop output.

### Apple Sidecar

Apple's [Sidecar requirements and usage guide](https://support.apple.com/en-us/102597) documents extending or mirroring a Mac desktop on an iPad through USB or wirelessly. It offers the best native Apple integration in this set, but requires supported Apple hardware, compatible operating systems, and the Apple account/security conditions described by Apple. It is not available from a Linux host.

### Duet Display

Duet's [second-display product page](https://www.duetdisplay.com/duet-extend-to-a-second-display) describes wired and wireless extension to tablets. Duet's official desktop offerings are for macOS and Windows; no official Linux host is documented. It is a commercial alternative for users who can choose one of those host systems.

### Luna Display

Astropad's [Luna Display system requirements](https://support.astropad.com/en/articles/11835375-what-are-the-system-requirements-for-luna-display) list Mac and Windows hosts, iPad receiver requirements, and mandatory Luna hardware. The hardware-assisted approach offers a polished extended-display product but does not address the Linux/no-dongle requirement.

### spacedesk

The [spacedesk system requirements](https://manual.spacedesk.net/SystemRequirements.html) describe its supported primary machines and iOS viewer/network requirements. Its architecture uses TCP/IP networking and does not document Linux as a primary display host.

## Where TuxDisplay is stronger

### 1. Offline Linux-to-tablet USB is the core path

TuxDisplay does not treat cable use as USB Ethernet. usbmuxd carries the iPadOS connection and ADB forwards the Android receiver port over the trusted cable. Both work when the tablet has no Internet, Wi-Fi, cellular data, or tethering. This avoids the most common failure in browser-only approaches: obtaining and reaching a cable network address.

### 2. GNOME receives a real output

The virtual monitor belongs to Mutter and participates in GNOME's display layout. Users can move ordinary existing windows onto it. That is materially different from an isolated virtual desktop, mirroring a region, or remotely controlling the laptop's existing panel.

### 3. No account, subscription, or display dongle

The host is MIT-licensed, compatible OpenDisplay receivers are available without a subscription, and the preferred connection uses an ordinary data cable. The product can be used entirely offline after the receiver app and Debian dependencies are present. The third-party Android receiver is separately licensed under GPL-3.0.

### 4. Compatibility paths are included

Safari/MJPEG and X11/noVNC are not as efficient as the OpenDisplay route, but they keep the package useful when direct USB or GNOME's virtual-monitor API is unavailable.

## Where alternatives are stronger

- **Desktop breadth:** Weylus and Deskreen support more host operating systems; the experimental OpenDisplay Linux sender covers KDE Plasma and Hyprland.
- **Input richness:** Weylus documents pressure, tilt, and multi-touch. TuxDisplay deliberately exposes only safe single-pointer semantics.
- **Encoding efficiency:** the OpenDisplay Linux sender documents hardware encoding; TuxDisplay currently uses software x264.
- **Commercial polish and support:** Sidecar, Duet, Luna Display, and spacedesk have mature product experiences and broader end-user support on their chosen platforms.
- **Remote use:** Sunshine/Moonlight is designed for high-performance network streaming beyond a physically attached second screen.
- **Automatic display adaptation:** mature commercial tools generally conceal more of the resolution, rotation, reconnect, and device-selection lifecycle.

## Product risks

| Risk | User impact | Mitigation or direction |
| --- | --- | --- |
| Mutter-private integration changes | A GNOME update can break native monitor creation | Test supported GNOME releases; isolate compositor calls; retain fallback |
| Software H.264 load | Heat, battery use, or dropped frames at high resolution | Add VA-API/NVENC/V4L2 encoder selection |
| Fixed configured mode | Borders and disruptive restarts on resolution changes | Use receiver hello dimensions and support safe dynamic reconfiguration |
| Single-pointer input | No multi-touch or Pencil pressure/tilt | Extend the protocol or add an input path with stable slot identity |
| USB-only OpenDisplay sender | Cable required even on a trusted LAN | Add optional authenticated Wi-Fi OpenDisplay discovery/transport |
| HTTP browser fallback | Unsafe on untrusted networks | Bind to selected interfaces; add TLS or a secure local tunnel option |
| GNOME-only native extension | KDE/Hyprland users get fallback rather than native output | Add compositor backends or coordinate with the OpenDisplay Linux sender |
| Debian-centric packaging | Installation friction on other distributions | Add reproducible Flatpak/RPM/Arch packaging where compositor permissions allow |

## Recommended positioning

> **Use an iPad or Android tablet as a real GNOME Wayland monitor over a normal USB cable—offline, without tethering, an account, or a dongle.**

This statement is specific and supportable. TuxDisplay should not claim universal Linux compositor support, full touch-display semantics, native-resolution negotiation, or superiority on latency until those areas are implemented and benchmarked.

## Suggested roadmap priorities

1. Negotiate a receiver-appropriate aspect ratio from the OpenDisplay hello and make mode changes reconnect cleanly.
2. Add hardware H.264 encoding with a tested software fallback.
3. Add a secure optional Wi-Fi OpenDisplay transport.
4. Provide native KDE Plasma and Hyprland backends, potentially sharing findings with the existing OpenDisplay Linux sender.
5. Design crash-safe multi-touch and Pencil pressure/tilt around explicit contact identities.
6. Add per-device authorization, interface binding, and encrypted browser access.
7. Publish signed, reproducible packages and a supported GNOME/distribution matrix.
8. Benchmark end-to-end latency, frame consistency, CPU use, and power at each preset against open-source alternatives.

## Bottom line

For a Linux user who specifically has GNOME Wayland, an iPad or Android tablet, and no usable network, TuxDisplay occupies a defensible gap: native desktop extension over direct USB with no extra hardware. Its most important engineering priorities are smoother resolution lifecycle, hardware encoding, broader compositor support, and stronger input/security semantics. Users who value stylus richness or cross-platform reach more than turnkey GNOME extension should also evaluate Weylus; KDE/Hyprland users should evaluate the experimental OpenDisplay Linux sender; Mac users with an iPad should start with Sidecar.
