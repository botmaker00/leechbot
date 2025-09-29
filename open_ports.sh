#!/bin/bash

# Function to extract port values from config.py
extract_port_values() {
    # Default port values
    BASE_URL_PORT=80
    RCLONE_SERVE_PORT=8080
    HYDRA_PORT=5076

    # Check if config.py exists
    if [ -f "config.py" ]; then
        echo "Reading port values from config.py..."

        # Extract BASE_URL_PORT
        BASE_URL_PORT_CONFIG=$(grep -E "^BASE_URL_PORT\s*=\s*[0-9]+" config.py | sed -E 's/^BASE_URL_PORT\s*=\s*([0-9]+).*/\1/')
        if [ ! -z "$BASE_URL_PORT_CONFIG" ]; then
            BASE_URL_PORT=$BASE_URL_PORT_CONFIG
            echo "Found BASE_URL_PORT: $BASE_URL_PORT"
        else
            echo "Using default BASE_URL_PORT: $BASE_URL_PORT"
        fi

        # Extract RCLONE_SERVE_PORT
        RCLONE_SERVE_PORT_CONFIG=$(grep -E "^RCLONE_SERVE_PORT\s*=\s*[0-9]+" config.py | sed -E 's/^RCLONE_SERVE_PORT\s*=\s*([0-9]+).*/\1/')
        if [ ! -z "$RCLONE_SERVE_PORT_CONFIG" ]; then
            RCLONE_SERVE_PORT=$RCLONE_SERVE_PORT_CONFIG
            echo "Found RCLONE_SERVE_PORT: $RCLONE_SERVE_PORT"
        else
            echo "Using default RCLONE_SERVE_PORT: $RCLONE_SERVE_PORT"
        fi

        # Extract HYDRA_IP to get port if specified
        HYDRA_IP_CONFIG=$(grep -E "^HYDRA_IP\s*=\s*\".*\"" config.py | sed -E 's/^HYDRA_IP\s*=\s*"(.*)".*$/\1/')
        if [ ! -z "$HYDRA_IP_CONFIG" ]; then
            # Extract port from URL if present (e.g., http://localhost:5076)
            HYDRA_PORT_FROM_IP=$(echo "$HYDRA_IP_CONFIG" | grep -oE ':[0-9]+' | cut -d':' -f2)
            if [ ! -z "$HYDRA_PORT_FROM_IP" ]; then
                HYDRA_PORT=$HYDRA_PORT_FROM_IP
                echo "Found HYDRA_PORT from HYDRA_IP: $HYDRA_PORT"
            else
                echo "Using default HYDRA_PORT: $HYDRA_PORT"
            fi
        else
            echo "Using default HYDRA_PORT: $HYDRA_PORT"
        fi
    else
        echo "config.py not found. Using default port values."
        echo "BASE_URL_PORT: $BASE_URL_PORT"
        echo "RCLONE_SERVE_PORT: $RCLONE_SERVE_PORT"
        echo "HYDRA_PORT: $HYDRA_PORT"
    fi
}

# Extract port values before applying rules
extract_port_values

# Flush All Rules (Reset iptables)
sudo iptables -F
sudo iptables -X
sudo iptables -t nat -F
sudo iptables -t nat -X
sudo iptables -t mangle -F
sudo iptables -t mangle -X

sudo ip6tables -F
sudo ip6tables -X
sudo ip6tables -t nat -F
sudo ip6tables -t nat -X
sudo ip6tables -t mangle -F
sudo ip6tables -t mangle -X

# Set Default Policies
sudo iptables -P INPUT ACCEPT
sudo iptables -P FORWARD ACCEPT
sudo iptables -P OUTPUT ACCEPT

sudo ip6tables -P INPUT ACCEPT
sudo ip6tables -P FORWARD ACCEPT
sudo ip6tables -P OUTPUT ACCEPT

# Allow loopback interface
sudo iptables -A INPUT -i lo -j ACCEPT
sudo ip6tables -A INPUT -i lo -j ACCEPT

# Allow established and related connections
sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo ip6tables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (port 22) - important to maintain access to your server
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport 22 -j ACCEPT

# Open necessary ports for AimLeechBot
# BASE_URL_PORT - Web interface
echo "Opening BASE_URL_PORT: $BASE_URL_PORT"
sudo iptables -A INPUT -p tcp --dport $BASE_URL_PORT -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport $BASE_URL_PORT -j ACCEPT

# RCLONE_SERVE_PORT - Rclone serve HTTP
echo "Opening RCLONE_SERVE_PORT: $RCLONE_SERVE_PORT"
sudo iptables -A INPUT -p tcp --dport $RCLONE_SERVE_PORT -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport $RCLONE_SERVE_PORT -j ACCEPT

# qBittorrent WebUI port (8090)
echo "Opening qBittorrent WebUI port: 8090"
sudo iptables -A INPUT -p tcp --dport 8090 -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport 8090 -j ACCEPT

# Aria2c RPC port (6800)
echo "Opening Aria2c RPC port: 6800"
sudo iptables -A INPUT -p tcp --dport 6800 -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport 6800 -j ACCEPT

# SABnzbd port (8070)
echo "Opening SABnzbd port: 8070"
sudo iptables -A INPUT -p tcp --dport 8070 -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport 8070 -j ACCEPT

# NZBHydra port
echo "Opening NZBHydra port: $HYDRA_PORT"
sudo iptables -A INPUT -p tcp --dport $HYDRA_PORT -j ACCEPT
sudo ip6tables -A INPUT -p tcp --dport $HYDRA_PORT -j ACCEPT

# Allow ICMP (ping)
sudo iptables -A INPUT -p icmp -j ACCEPT
sudo ip6tables -A INPUT -p ipv6-icmp -j ACCEPT

# Save the rules
echo "Saving firewall rules..."
sudo mkdir -p /etc/iptables
sudo iptables-save | sudo tee /etc/iptables/rules.v4
sudo ip6tables-save | sudo tee /etc/iptables/rules.v6

echo "Firewall rules have been applied and saved."
