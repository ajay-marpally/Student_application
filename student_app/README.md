# Student Exam Application

A production-ready Windows Student Exam Application with local AI proctoring.

## Features

- **Offline-first AI Proctoring**: All detection runs locally on CPU
- **10 Detection Scenarios**: Head turns, gaze tracking, phone detection, audio monitoring
- **Secure Evidence Handling**: SHA-256 integrity, AES encryption
- **Kiosk Mode**: Fullscreen enforcement with fallback detection
- **Supabase Integration**: Exam data, answers, and evidence upload

## Quick Start

### Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m student_app.app.main
```

### Build .exe

```bash
pip install pyinstaller
pyinstaller student_app.spec --clean
# Output: dist/student_client.exe
```

## Project Structure

```
student_app/
├── app/
│   ├── main.py              # Application entry point
│   ├── config.py            # Configuration management
│   ├── auth.py              # Authentication module
│   ├── exam_engine.py       # Exam flow controller
│   ├── ui/                  # PySide6 UI components
│   ├── ai/                  # Local AI detection
│   ├── buffer/              # Video/audio buffering
│   ├── storage/             # Supabase integration
│   ├── security/            # Tamper detection
│   ├── kiosk/               # Fullscreen enforcement
│   ├── db/                  # SQLite queue
│   └── utils/               # Helpers
├── tests/                   # Unit and integration tests
└── build/                   # PyInstaller assets
```

## Configuration

Set environment variables or use `.env`:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-key
```

## Documentation

- [Threat Model](docs/threat_model.md)
- [Forensics Checklist](docs/forensics_checklist.md)
- [Kiosk Setup Guide](docs/kiosk_setup.md)

## License

Proprietary - For authorized exam centers only.
