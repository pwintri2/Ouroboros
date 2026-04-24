#!/bin/bash

# Docker PATH Setup for Negesydd
# Run this script to enable Docker access

echo "🐳 Setting up Docker access..."

# Check if docker is installed
if [ ! -x /usr/bin/docker ]; then
    echo "✗ Docker not found at /usr/bin/docker"
    exit 1
fi

# Add docker to current shell PATH
export PATH="/usr/bin:$PATH"

# Verify docker is accessible
if ! command -v docker &> /dev/null; then
    echo "✗ Failed to add Docker to PATH"
    exit 1
fi

# Test docker
echo "✓ Docker found: $(docker --version)"

# Check if docker daemon is running
if ! docker ps &> /dev/null; then
    echo "⚠️  Docker daemon not responding"
    echo "   Start Docker Desktop and try again"
    exit 1
fi

echo "✓ Docker daemon is running"

# Check if docker is in bashrc
if ! grep -q "export PATH.*docker" ~/.bashrc 2>/dev/null; then
    echo ""
    echo "→ Adding Docker to ~/.bashrc for permanent access..."
    
    # Add to bashrc
    cat >> ~/.bashrc << 'EOF'

# Docker PATH (added by Negesydd setup)
export PATH="/usr/bin:$PATH"
EOF
    
    echo "✓ Docker PATH added to ~/.bashrc"
    echo "   Run: source ~/.bashrc  (or restart terminal)"
else
    echo "✓ Docker already in ~/.bashrc"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ Docker setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. Run: source ~/.bashrc"
echo "  2. Verify: docker --version"
echo "  3. Build sandbox: ./sandbox-build.sh init"
echo "  4. Build image: ./sandbox-build.sh build"
echo ""
