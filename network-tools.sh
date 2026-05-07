#!/bin/bash
set -e

OUROBOROS_CONTAINER="wintripai-ouroboros-backend-1"

usage() {
    echo "WintripAI Network Connectivity Tools"
    echo ""
    echo "Usage: ./network-tools.sh <command>"
    echo ""
    echo "Commands:"
    echo "  status              Check internet connectivity"
    echo "  ping <host>         Ping an external host"
    echo "  dns <hostname>      Test DNS resolution"
    echo "  curl <url>          Test HTTP/HTTPS requests"
    echo "  brave-health        Check Brave search services"
    echo "  chroma-health       Check Chroma connectivity"
    echo "  full-diagnostic     Run comprehensive network diagnostics"
    echo "  routes              Show network routes and interfaces"
    echo ""
}

status() {
    echo "=== Internet Connectivity Status ==="
    docker exec "$OUROBOROS_CONTAINER" ping -c 1 8.8.8.8 > /dev/null 2>&1 && echo "[OK] External internet: CONNECTED" || echo "[FAIL] External internet: FAILED"
    docker exec "$OUROBOROS_CONTAINER" nslookup google.com > /dev/null 2>&1 && echo "[OK] DNS resolution: WORKING" || echo "[FAIL] DNS resolution: FAILED"
    docker exec "$OUROBOROS_CONTAINER" curl -s https://www.google.com > /dev/null 2>&1 && echo "[OK] HTTPS: WORKING" || echo "[FAIL] HTTPS: FAILED"
    docker exec "$OUROBOROS_CONTAINER" curl -s http://brave-search-1:8080 > /dev/null 2>&1 && echo "[OK] Brave Search 1: CONNECTED" || echo "[FAIL] Brave Search 1: FAILED"
    docker exec "$OUROBOROS_CONTAINER" curl -s http://brave-search-2:8080 > /dev/null 2>&1 && echo "[OK] Brave Search 2: CONNECTED" || echo "[FAIL] Brave Search 2: FAILED"
    docker exec "$OUROBOROS_CONTAINER" curl -s http://chroma:8000 > /dev/null 2>&1 && echo "[OK] Chroma DB: CONNECTED" || echo "[FAIL] Chroma DB: FAILED"
}

ping_host() {
    local host="$1"
    echo "=== Pinging $host ==="
    docker exec "$OUROBOROS_CONTAINER" ping -c 4 "$host"
}

dns_test() {
    local hostname="$1"
    echo "=== DNS Resolution Test: $hostname ==="
    docker exec "$OUROBOROS_CONTAINER" nslookup "$hostname"
}

curl_test() {
    local url="$1"
    echo "=== Testing URL: $url ==="
    docker exec "$OUROBOROS_CONTAINER" curl -v "$url" 2>&1 | head -30
}

brave_health() {
    echo "=== Brave Search Services Health ==="
    echo ""
    echo "Brave Search 1:"
    docker exec "$OUROBOROS_CONTAINER" curl -s http://brave-search-1:8080 && echo "Connected" || echo "Failed"
    echo ""
    echo "Brave Search 2:"
    docker exec "$OUROBOROS_CONTAINER" curl -s http://brave-search-2:8080 && echo "Connected" || echo "Failed"
    echo ""
    echo "Container logs (brave-search containers):"
    docker logs --tail 10 $(docker ps -q -f "ancestor=mcp/brave-search" | head -2) 2>/dev/null || echo "No Brave containers found"
}

chroma_health() {
    echo "=== Chroma DB Health ==="
    docker exec "$OUROBOROS_CONTAINER" curl -s http://chroma:8000/api/v1/heartbeat
    echo ""
}

full_diagnostic() {
    echo "================================================"
    echo "  WintripAI Network Diagnostic Report"
    echo "================================================"
    echo ""

    status
    echo ""

    echo "=== Network Interfaces ==="
    docker exec "$OUROBOROS_CONTAINER" ip addr show
    echo ""

    echo "=== Routes ==="
    docker exec "$OUROBOROS_CONTAINER" ip route show
    echo ""

    echo "=== DNS Configuration ==="
    docker exec "$OUROBOROS_CONTAINER" cat /etc/resolv.conf
    echo ""

    echo "=== Environment Variables ==="
    docker exec "$OUROBOROS_CONTAINER" env | grep -i "proxy\|brave\|search\|http" || echo "No proxy/search vars set"
    echo ""

    echo "=== Docker Networks ==="
    docker network inspect wintripai_wintrip-network | jq '.[] | {Name, Containers: (.Containers | length)}'
    echo ""

    echo "=== Running Services ==="
    docker compose -f /home/pwintri2/WintripAI/docker-compose.yml ps
}

routes() {
    echo "=== Network Routes ==="
    docker exec "$OUROBOROS_CONTAINER" ip route show
    echo ""
    echo "=== Network Interfaces ==="
    docker exec "$OUROBOROS_CONTAINER" ip addr show
    echo ""
    echo "=== Network Statistics ==="
    docker exec "$OUROBOROS_CONTAINER" netstat -tuln | grep LISTEN || docker exec "$OUROBOROS_CONTAINER" ss -tuln | grep LISTEN
}

if [ $# -eq 0 ]; then
    usage
    exit 1
fi

case "$1" in
    status)
        status
        ;;
    ping)
        ping_host "${2:-8.8.8.8}"
        ;;
    dns)
        dns_test "${2:-google.com}"
        ;;
    curl)
        curl_test "${2:-https://www.google.com}"
        ;;
    brave-health)
        brave_health
        ;;
    chroma-health)
        chroma_health
        ;;
    full-diagnostic)
        full_diagnostic
        ;;
    routes)
        routes
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac
