# Code Signing Guide for Student Exam Application

## Why Code Sign?

Code signing your `.exe` file is **essential** for:
- Avoiding antivirus false positives
- Establishing trust with Windows SmartScreen
- Ensuring users can run the application without security warnings
- Proving the software hasn't been tampered with

## Getting a Code Signing Certificate

### Option 1: Extended Validation (EV) Certificate (Recommended)
- **Best for**: Production deployments
- **Cost**: $300-500/year
- **Providers**: DigiCert, Sectigo, GlobalSign
- **Advantages**: Immediate SmartScreen reputation, hardware token for security

### Option 2: Standard Code Signing Certificate
- **Best for**: Development/testing
- **Cost**: $100-200/year
- **Providers**: Sectigo, Comodo, SSL.com
- **Note**: Requires reputation building with SmartScreen

### Option 3: Self-Signed (Development Only)
- **Best for**: Internal testing
- **Cost**: Free
- **Note**: Users will see warnings, not for production

## Signing Process

### Step 1: Install Windows SDK
```powershell
# Install Windows SDK (includes signtool.exe)
# Download from: https://developer.microsoft.com/windows/downloads/windows-sdk/
```

### Step 2: Build the .exe
```bash
pyinstaller student_app.spec --clean
# Output: dist/student_client.exe
```

### Step 3: Sign the Executable

**Using PFX Certificate:**
```powershell
# Sign with timestamp (important for long-term validity)
signtool sign /f certificate.pfx /p password /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\student_client.exe"

# Verify signature
signtool verify /pa /v "dist\student_client.exe"
```

**Using Hardware Token (EV Certificate):**
```powershell
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "dist\student_client.exe"
```

### Step 4: Verify Signature
```powershell
# Check signature details
signtool verify /pa /v "dist\student_client.exe"

# Or right-click the file > Properties > Digital Signatures
```

## PyInstaller Integration

The spec file is already configured for signing. To add during build:

```python
# In student_app.spec
exe = EXE(
    ...
    codesign_identity='Your Certificate Name',  # macOS
    # For Windows, sign after build
)
```

## Post-Build Signing Script

Create `scripts/sign_release.bat`:

```batch
@echo off
set SIGNTOOL="C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe"
set TIMESTAMP=http://timestamp.digicert.com
set CERT=path\to\certificate.pfx
set PASSWORD=your_password

echo Signing student_client.exe...
%SIGNTOOL% sign /f %CERT% /p %PASSWORD% /tr %TIMESTAMP% /td sha256 /fd sha256 "dist\student_client.exe"

echo Verifying signature...
%SIGNTOOL% verify /pa /v "dist\student_client.exe"

echo Done!
pause
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Publisher: Unknown" | Certificate not trusted, use EV certificate |
| SmartScreen blocks | Build reputation by signing consistently |
| Signature invalid | Check timestamp server and certificate validity |
| "Unable to find signtool" | Install Windows SDK |

## Certificate Storage

> ⚠️ **IMPORTANT**: Never commit certificates or passwords to git!

Store securely:
- Use environment variables for passwords
- Keep PFX files in secure storage
- Use hardware tokens for EV certificates

## Resources

- [Microsoft Code Signing Documentation](https://docs.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools)
- [DigiCert Code Signing Guide](https://www.digicert.com/signing/code-signing-certificates)
- [PyInstaller Code Signing](https://pyinstaller.readthedocs.io/en/stable/usage.html#windows)
