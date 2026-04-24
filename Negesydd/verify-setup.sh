#!/bin/bash

# Negesydd Setup Verification Script
# Run this to confirm Docker sandbox is ready

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "NEGESYDD DOCKER SANDBOX VERIFICATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null)
    echo "   ✓ $DOCKER_VERSION"
else
    echo "   ✗ Docker not found in PATH"
    echo "   Run: source ~/.bashrc"
    exit 1
fi

# Check Docker daemon
echo "2. Checking Docker daemon..."
if docker ps &> /dev/null; then
    echo "   ✓ Docker daemon running"
else
    echo "   ✗ Docker daemon not responding"
    echo "   Start Docker Desktop"
    exit 1
fi

# Check sandbox image
echo "3. Checking sandbox image..."
if docker image inspect negesydd:dev-sandbox &> /dev/null; then
    SIZE=$(docker image inspect negesydd:dev-sandbox --format='{{.Size}}' | numfmt --to=iec-i --suffix=B 2>/dev/null || docker image inspect negesydd:dev-sandbox --format='{{.Size}}')
    echo "   ✓ Image ready (negesydd:dev-sandbox)"
else
    echo "   ✗ Image not found"
    echo "   Run: ./sandbox-build.sh build"
    exit 1
fi

# Check Docker volume
echo "4. Checking Docker volume..."
if docker volume inspect negesydd-dev &> /dev/null; then
    echo "   ✓ Volume created (negesydd-dev)"
else
    echo "   ✗ Volume not found"
    echo "   Run: ./sandbox-build.sh init"
    exit 1
fi

# Check test directory
echo "5. Checking test directory..."
if [ -d "tests" ] && [ -f "tests/__init__.py" ]; then
    echo "   ✓ Test directory ready"
else
    echo "   ✗ Test directory missing"
    exit 1
fi

# Check script permissions
echo "6. Checking script permissions..."
if [ -x "sandbox-build.sh" ]; then
    echo "   ✓ sandbox-build.sh executable"
else
    echo "   ✗ sandbox-build.sh not executable"
    chmod +x sandbox-build.sh
    echo "   ✓ Fixed permissions"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✓ ALL CHECKS PASSED - READY FOR IMPLEMENTATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. Ask Codex to implement: logger.py"
echo "  2. Save to: /home/pwintri2/Negesydd/logger.py"
echo "  3. Test: ./sandbox-build.sh test logger"
echo ""
