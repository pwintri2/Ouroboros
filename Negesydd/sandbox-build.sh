#!/bin/bash

# Negesydd Docker Sandbox Build & Test Script
# Usage: ./sandbox-build.sh [init|build|test|test-all|shell|clean]

set -e

PROJECT_DIR="/home/pwintri2/Negesydd"
IMAGE_NAME="negesydd:dev-sandbox"
VOLUME_NAME="negesydd-dev"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Initialize sandbox (create directories, volumes)
init_sandbox() {
    print_header "INITIALIZING SANDBOX"
    
    cd "$PROJECT_DIR"
    
    # Create test directory
    mkdir -p tests
    touch tests/__init__.py
    print_success "Created tests/ directory"
    
    # Create Docker volume for persistence
    if ! docker volume inspect $VOLUME_NAME > /dev/null 2>&1; then
        docker volume create $VOLUME_NAME
        print_success "Created Docker volume: $VOLUME_NAME"
    else
        print_info "Volume $VOLUME_NAME already exists"
    fi
    
    # Create logs directory
    mkdir -p logs
    print_success "Created logs/ directory"
    
    print_success "Sandbox initialized"
}

# Build Docker image
build_sandbox() {
    print_header "BUILDING SANDBOX IMAGE"
    
    cd "$PROJECT_DIR"
    
    if [ ! -f "Dockerfile.sandbox" ]; then
        print_error "Dockerfile.sandbox not found"
        exit 1
    fi
    
    print_info "Building $IMAGE_NAME..."
    docker build -f Dockerfile.sandbox -t $IMAGE_NAME . --progress=plain
    
    print_success "Image built: $IMAGE_NAME"
    
    # Show image info
    docker images | grep negesydd
}

# Run tests for specific module
test_module() {
    local module=$1
    
    if [ -z "$module" ]; then
        print_error "Usage: $0 test <module_name>"
        echo "  Available: logger, message_types, agent_pool, message_queue"
        exit 1
    fi
    
    print_header "TESTING: $module"
    
    docker run --rm \
        -v "$PROJECT_DIR:/negesydd" \
        -v "$VOLUME_NAME:/negesydd/.venv" \
        $IMAGE_NAME \
        bash -c "cd /negesydd && python -m pytest tests/test_${module}.py -v --tb=short"
    
    print_success "Test completed: $module"
}

# Run all tests
test_all() {
    print_header "RUNNING ALL TESTS"
    
    docker run --rm \
        -v "$PROJECT_DIR:/negesydd" \
        -v "$VOLUME_NAME:/negesydd/.venv" \
        $IMAGE_NAME \
        bash -c "cd /negesydd && python -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing"
    
    print_success "All tests completed"
}

# Interactive shell
shell_sandbox() {
    print_header "LAUNCHING INTERACTIVE SHELL"
    print_info "You are now inside the sandbox container"
    print_info "Type 'exit' to return to host"
    echo ""
    
    docker run -it \
        -v "$PROJECT_DIR:/negesydd" \
        -v "$VOLUME_NAME:/negesydd/.venv" \
        -e PYTHONUNBUFFERED=1 \
        $IMAGE_NAME
}

# Clean up sandbox
clean_sandbox() {
    print_header "CLEANING UP"
    
    print_info "Removing image: $IMAGE_NAME"
    docker rmi -f $IMAGE_NAME 2>/dev/null || print_info "Image not found"
    
    print_info "Removing volume: $VOLUME_NAME"
    docker volume rm $VOLUME_NAME 2>/dev/null || print_info "Volume not found"
    
    print_info "Removing Docker build cache"
    docker builder prune -f > /dev/null
    
    print_success "Cleanup completed"
}

# Show usage
usage() {
    cat << EOF
${BLUE}Negesydd Docker Sandbox - Build & Test Utility${NC}

${YELLOW}Usage:${NC}
    ./sandbox-build.sh [command] [arguments]

${YELLOW}Commands:${NC}
    init        Initialize sandbox (create directories, volumes)
    build       Build Docker image for sandbox
    test        Run specific module tests
    test-all    Run all tests
    shell       Launch interactive shell in sandbox
    clean       Remove image and volumes

${YELLOW}Examples:${NC}
    ./sandbox-build.sh init
    ./sandbox-build.sh build
    ./sandbox-build.sh test logger
    ./sandbox-build.sh test-all
    ./sandbox-build.sh shell
    ./sandbox-build.sh clean

${YELLOW}Full Workflow:${NC}
    1. ./sandbox-build.sh init
    2. ./sandbox-build.sh build
    3. Implement module with Codex
    4. ./sandbox-build.sh test <module_name>
    5. Repeat steps 3-4 for each module
    6. ./sandbox-build.sh test-all
    7. ./sandbox-build.sh shell (for debugging)
    8. ./sandbox-build.sh clean (when done)

EOF
}

# Main
case "${1:-help}" in
    init)
        init_sandbox
        ;;
    build)
        init_sandbox
        build_sandbox
        ;;
    test)
        test_module "$2"
        ;;
    test-all)
        test_all
        ;;
    shell)
        shell_sandbox
        ;;
    clean)
        clean_sandbox
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        print_error "Unknown command: $1"
        usage
        exit 1
        ;;
esac

print_success "Done!"
