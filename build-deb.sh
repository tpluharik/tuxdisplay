#!/bin/sh
set -eu

td_project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
td_version=0.4.27
# Keep archive metadata stable across repeated builds. Update this epoch from
# the newest Debian changelog entry whenever the package version changes.
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1794417062}
export SOURCE_DATE_EPOCH
td_build_dir="$td_project_dir/build"
td_package_root="$td_build_dir/tuxdisplay_${td_version}_all"
td_output_dir="$td_project_dir/dist"
td_output="$td_output_dir/tuxdisplay_${td_version}_all.deb"

rm -rf "$td_package_root"
mkdir -p "$td_build_dir" "$td_output_dir"
cp -a "$td_project_dir/packaging/." "$td_package_root/"
find "$td_package_root" -type f -name "*.pyc" -delete
find "$td_package_root" -type d -name __pycache__ -empty -delete
unlink "$td_package_root/changelog"
find "$td_package_root/man" -type f -delete
find "$td_package_root/man" -depth -type d -empty -delete

mkdir -p "$td_package_root/usr/share/doc/tuxdisplay"
cp "$td_project_dir/README.md" "$td_package_root/usr/share/doc/tuxdisplay/README.md"
cp "$td_project_dir/CONTRIBUTING.md" "$td_package_root/usr/share/doc/tuxdisplay/CONTRIBUTING.md"
cp -a "$td_project_dir/docs" "$td_package_root/usr/share/doc/tuxdisplay/"
cp "$td_project_dir/LICENSE" "$td_package_root/usr/share/doc/tuxdisplay/copyright"
gzip -9n -c "$td_project_dir/packaging/changelog" > "$td_package_root/usr/share/doc/tuxdisplay/changelog.gz"
mkdir -p "$td_package_root/usr/share/man/man1" "$td_package_root/usr/share/man/man8"
gzip -9n -c "$td_project_dir/packaging/man/tuxdisplay.1" > "$td_package_root/usr/share/man/man1/tuxdisplay.1.gz"
gzip -9n -c "$td_project_dir/packaging/man/tuxdisplay-usb.8" > "$td_package_root/usr/share/man/man8/tuxdisplay-usb.8.gz"

find "$td_package_root" -type d -exec chmod 0755 {} +
find "$td_package_root" -type f -exec chmod 0644 {} +
chmod 0755 \
    "$td_package_root/DEBIAN/postinst" \
    "$td_package_root/DEBIAN/prerm" \
    "$td_package_root/DEBIAN/postrm" \
    "$td_package_root/usr/bin/tuxdisplay" \
    "$td_package_root/usr/sbin/tuxdisplay-usb" \
    "$td_package_root/usr/lib/tuxdisplay/tuxdisplay-session" \
    "$td_package_root/usr/lib/tuxdisplay/tuxdisplay-wayland" \
    "$td_package_root/usr/lib/tuxdisplay/tuxdisplay-welcome" \
    "$td_package_root/usr/lib/tuxdisplay/update-helper"

ln -s ../../novnc/vnc.html "$td_package_root/usr/share/tuxdisplay/web/vnc.html"
ln -s ../../novnc/vnc_lite.html "$td_package_root/usr/share/tuxdisplay/web/vnc_lite.html"
ln -s ../../novnc/app "$td_package_root/usr/share/tuxdisplay/web/app"
ln -s ../../novnc/core "$td_package_root/usr/share/tuxdisplay/web/core"
ln -s ../../novnc/vendor "$td_package_root/usr/share/tuxdisplay/web/vendor"

(cd "$td_package_root" && find usr etc -type f -print0 | sort -z | xargs -0 md5sum) > "$td_package_root/DEBIAN/md5sums"
chmod 0644 "$td_package_root/DEBIAN/control" "$td_package_root/DEBIAN/md5sums"

# dpkg archives source mtimes by default. Normalize the complete staged tree so
# a fresh clone and a long-lived checkout produce byte-identical packages.
find "$td_package_root" -print0 | xargs -0 touch --no-dereference --date="@$SOURCE_DATE_EPOCH"

# Store the Debian archive members without compression. Compression output can
# vary between the dpkg/xz versions used by developer machines and Ubuntu CI;
# the staged bytes and metadata are already normalized, so uncompressed members
# make the signed package reproducible across those environments as well.
dpkg-deb --root-owner-group --uniform-compression -Znone --build "$td_package_root" "$td_output"
(cd "$td_output_dir" && sha256sum "$(basename "$td_output")" > SHA256SUMS)
echo "$td_output"
