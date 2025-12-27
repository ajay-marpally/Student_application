# Assets Directory

This directory contains assets for the Windows executable:

## Required Files

### icon.ico
Application icon for the Windows executable. 

**To add an icon:**
1. Create or download an icon (256x256 PNG recommended)
2. Convert to ICO format using an online converter or:
   ```bash
   # Using ImageMagick
   convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
   ```
3. Place `icon.ico` in this directory

### version_info.txt
Windows version information embedded in the executable.
- Already created with default values
- Edit to update version numbers before release

## Build

Once assets are in place, build with:
```bash
pyinstaller student_app.spec --clean
```

The spec file automatically detects if icon.ico exists and includes it.
