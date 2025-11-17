#!/bin/bash
#
# Build script for Context OS macOS app
#
# This script:
# 1. Converts the PNG logo to ICNS format
# 2. Runs PyInstaller to create the .app bundle
# 3. Optionally creates a DMG installer
#
# Usage:
#   bash build.sh [--skip-icon] [--no-dmg]
#
# Options:
#   --skip-icon    Skip icon conversion (use existing icon.icns)
#   --no-dmg       Don't create DMG installer
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_ICON=false
NO_DMG=false

for arg in "$@"; do
    case $arg in
        --skip-icon)
            SKIP_ICON=true
            shift
            ;;
        --no-dmg)
            NO_DMG=true
            shift
            ;;
        *)
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Context OS Build Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Step 1: Convert icon
if [ "$SKIP_ICON" = false ]; then
    echo -e "${YELLOW}[1/4] Converting PNG logo to ICNS format...${NC}"

    if [ ! -f "docs/logo_icon.png" ]; then
        echo -e "${RED}Error: docs/logo_icon.png not found${NC}"
        exit 1
    fi

    # Check if required packages are installed
    python3 -c "import PIL" 2>/dev/null || {
        echo -e "${YELLOW}Installing Pillow for icon conversion...${NC}"
        pip3 install pillow
    }

    # Convert PNG to ICNS
    python3 build/convert_icon_from_png.py

    if [ ! -f "build/icon.icns" ]; then
        echo -e "${RED}Error: Icon conversion failed${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Icon converted successfully${NC}"
    echo ""
else
    echo -e "${YELLOW}[1/4] Skipping icon conversion${NC}"
    if [ ! -f "build/icon.icns" ]; then
        echo -e "${RED}Warning: build/icon.icns not found and --skip-icon specified${NC}"
    fi
    echo ""
fi

# Step 2: Clean previous builds
echo -e "${YELLOW}[2/4] Cleaning previous builds...${NC}"
rm -rf build/ContextOS dist/ContextOS.app dist/ContextOS

echo -e "${GREEN}✓ Cleaned${NC}"
echo ""

# Step 3: Run PyInstaller
echo -e "${YELLOW}[3/4] Building macOS app with PyInstaller...${NC}"

if [ ! -f "ContextOS.spec" ]; then
    echo -e "${RED}Error: ContextOS.spec not found${NC}"
    exit 1
fi

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${YELLOW}PyInstaller not found. Installing...${NC}"
    pip3 install pyinstaller
fi

pyinstaller --clean ContextOS.spec

if [ ! -d "dist/ContextOS.app" ]; then
    echo -e "${RED}Error: Build failed - ContextOS.app not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ App built successfully${NC}"
echo -e "${GREEN}  Location: dist/ContextOS.app${NC}"

# Get app size
APP_SIZE=$(du -sh dist/ContextOS.app | cut -f1)
echo -e "${GREEN}  Size: ${APP_SIZE}${NC}"
echo ""

# Step 4: Create DMG (optional)
if [ "$NO_DMG" = false ]; then
    echo -e "${YELLOW}[4/4] Creating DMG installer with Applications symlink...${NC}"

    DMG_NAME="ContextOS"
    DMG_FILE="dist/${DMG_NAME}.dmg"
    DMG_TEMP_DIR="dist/dmg_temp"

    # Remove existing DMG and temp directory
    rm -f "$DMG_FILE"
    rm -rf "$DMG_TEMP_DIR"

    # Create temporary directory for DMG contents
    mkdir -p "$DMG_TEMP_DIR"

    # Copy app to temp directory
    echo "  Copying ContextOS.app..."
    cp -R "dist/ContextOS.app" "$DMG_TEMP_DIR/"

    # Create Applications symlink
    echo "  Creating Applications symlink..."
    ln -s /Applications "$DMG_TEMP_DIR/Applications"

    # Create DMG from temp directory
    echo "  Building DMG..."
    hdiutil create -volname "$DMG_NAME" \
                   -srcfolder "$DMG_TEMP_DIR" \
                   -ov \
                   -format UDZO \
                   "$DMG_FILE"

    # Clean up temp directory
    rm -rf "$DMG_TEMP_DIR"

    if [ -f "$DMG_FILE" ]; then
        DMG_SIZE=$(du -sh "$DMG_FILE" | cut -f1)
        echo -e "${GREEN}✓ DMG created successfully${NC}"
        echo -e "${GREEN}  Location: ${DMG_FILE}${NC}"
        echo -e "${GREEN}  Size: ${DMG_SIZE}${NC}"
        echo -e "${GREEN}  Includes: Applications symlink for easy drag-and-drop install${NC}"
    else
        echo -e "${RED}Warning: DMG creation failed${NC}"
    fi
    echo ""
else
    echo -e "${YELLOW}[4/4] Skipping DMG creation${NC}"
    echo ""
fi

# Final summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Build completed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Application: ${GREEN}dist/ContextOS.app${NC}"
if [ "$NO_DMG" = false ] && [ -f "dist/${DMG_NAME}.dmg" ]; then
    echo -e "Installer:   ${GREEN}dist/${DMG_NAME}.dmg${NC}"
fi
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Test the app: open dist/ContextOS.app"
echo "2. Check clipboard monitoring works"
echo "3. Verify settings can be changed"
echo "4. Test all tools (translator, calculator)"
echo ""
echo -e "${BLUE}To distribute:${NC}"
echo "- For testing: Share the .app directly"
echo "- For users: Share the .dmg installer"
echo ""
echo -e "${YELLOW}Note:${NC} First time users may need to:"
echo '- Right-click the app and select "Open" to bypass Gatekeeper'
echo "- Grant clipboard access permission when prompted"
echo ""
