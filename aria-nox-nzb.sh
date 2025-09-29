#!/bin/bash

# Silent execution - redirect all output to /dev/null
exec >/dev/null 2>&1

# Start qBittorrent-nox daemon (check if not already running)
if ! pgrep -f "xnox" > /dev/null 2>&1; then
    # Try to start qBittorrent, ignore errors if already running
    xnox -d --profile="$(pwd)" 2>/dev/null || true &
fi

# Start SABnzbd daemon (check if not already running)
if ! pgrep -f "xnzb" > /dev/null 2>&1; then
    # Try to start SABnzbd, ignore errors if already running
    xnzb -f sabnzbd/SABnzbd.ini -s :::8070 -b 0 -d -c -l 0 --console 2>/dev/null || true &
fi

# Start aria2c daemon with tracker list (check if not already running)
if ! pgrep -f "xria" > /dev/null 2>&1; then
    # Get tracker list silently
    tracker_list=$(curl -Ns https://ngosang.github.io/trackerslist/trackers_all_http.txt 2>/dev/null |
                   awk '$0' | tr '\n\n' ',')

    # Try to start aria2c, ignore errors if already running
    xria \
        --allow-overwrite=true \
        --auto-file-renaming=true \
        --bt-enable-lpd=true \
        --bt-detach-seed-only=true \
        --bt-remove-unselected-file=true \
        --bt-tracker="[$tracker_list]" \
        --bt-max-peers=0 \
        --enable-rpc=true \
        --rpc-max-request-size=1024M \
        --max-connection-per-server=10 \
        --max-concurrent-downloads=1000 \
        --split=10 \
        --seed-ratio=0 \
        --check-integrity=true \
        --continue=true \
        --daemon=true \
        --disk-cache=40M \
        --force-save=true \
        --min-split-size=10M \
        --follow-torrent=mem \
        --check-certificate=false \
        --optimize-concurrent-downloads=true \
        --http-accept-gzip=true \
        --max-file-not-found=0 \
        --max-tries=20 \
        --peer-id-prefix=-qB4520- \
        --reuse-uri=true \
        --content-disposition-default-utf8=true \
        --user-agent=Wget/1.12 \
        --peer-agent=qBittorrent/4.5.2 \
        --quiet=true \
        --summary-interval=0 \
        --max-upload-limit=1K 2>/dev/null || true &
fi

# Wait for all background processes to start
wait