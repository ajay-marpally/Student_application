# Student Exam Application - Threat Model

## Overview

This document describes the security threats, attack vectors, and mitigations for the Student Exam Application.

## System Assets

| Asset | Description | Sensitivity |
|-------|-------------|-------------|
| Student Identity | Hall ticket, biometrics | HIGH |
| Exam Questions | Exam content | HIGH |
| Answers | Student responses | HIGH |
| Evidence Clips | Video evidence of violations | HIGH |
| Credentials | Supabase API keys | CRITICAL |

## Threat Actors

1. **Exam Cheaters** - Students attempting to gain unfair advantage
2. **External Helpers** - Individuals assisting students during exams
3. **Technical Attackers** - Those attempting to bypass security controls
4. **Insider Threats** - Exam center staff with system access

## Attack Vectors & Mitigations

### 1. Application Bypass

| Attack | Risk | Mitigation |
|--------|------|------------|
| Close application | HIGH | Fullscreen enforcement, close prevention |
| Alt+Tab to other apps | HIGH | Hotkey blocking (elevated), detection fallback |
| Task Manager access | MEDIUM | Registry-based disable (elevated) |
| Ctrl+Alt+Del | MEDIUM | Cannot block (OS-level), detect and log |

### 2. Screen Capture

| Attack | Risk | Mitigation |
|--------|------|------------|
| Screen recorders | HIGH | Process detection (OBS, Camtasia, etc.) |
| Remote desktop | HIGH | Session detection, process monitoring |
| Virtual cameras | MEDIUM | Driver detection |
| Screenshots | MEDIUM | PrintScreen blocking (attempted) |

### 3. Identity Fraud

| Attack | Risk | Mitigation |
|--------|------|------------|
| Wrong person taking exam | HIGH | Biometric verification, continuous face detection |
| Photo/video of student | MEDIUM | Face mesh analysis (anti-spoofing) |
| Multiple persons helping | HIGH | Face count monitoring |

### 4. AI Evasion

| Attack | Risk | Mitigation |
|--------|------|------------|
| Camera covering | HIGH | Face absent detection |
| Minimal head movement | MEDIUM | Multi-factor detection (gaze, pose, audio) |
| Looking at phone quickly | MEDIUM | Frequency-based detection |
| Mirror/reflection use | LOW | Gaze tracking analysis |

### 5. Data Tampering

| Attack | Risk | Mitigation |
|--------|------|------------|
| Modify evidence files | HIGH | SHA-256 hash verification |
| Intercept uploads | MEDIUM | HTTPS, encrypted payloads |
| Clock manipulation | MEDIUM | Server time verification |
| Debugger attachment | HIGH | Anti-debug detection |

### 6. Application Tampering

| Attack | Risk | Mitigation |
|--------|------|------------|
| Modify .exe | HIGH | Integrity check on startup |
| PyInstaller extraction | MEDIUM | Code obfuscation (limited) |
| Memory manipulation | MEDIUM | Anti-debug checks |
| DLL injection | MEDIUM | Process monitoring |

### 7. Environment Attacks

| Attack | Risk | Mitigation |
|--------|------|------------|
| Virtual machine | MEDIUM | VM detection (registry, processes) |
| Sandbox execution | MEDIUM | Environment fingerprinting |
| Modified Windows | LOW | Integrity checks |

## Security Controls Summary

| Control | Implementation |
|---------|----------------|
| Integrity Verification | SHA-256 hash of binaries |
| Debugger Detection | IsDebuggerPresent(), TracerPid |
| VM Detection | Registry keys, file checks, process names |
| Process Monitoring | Screen recorders, debuggers, remote desktop |
| Encryption | AES for evidence, HTTPS for transport |
| Audit Logging | All actions logged with timestamps |
| Fullscreen Lock | Qt flags, Windows API, focus monitoring |

## Residual Risks

1. **Ctrl+Alt+Del** - Cannot be blocked at application level
2. **Physical World** - Notes, second devices out of camera view
3. **Audio Bypass** - Earpiece assistance
4. **Sophisticated Attacks** - Kernel-level bypasses

## Recommendations

1. **Exam Center Controls** - Physical security, metal detectors
2. **Network Monitoring** - Block unauthorized traffic
3. **Random Verification** - Manual spot-checks by invigilators
4. **Post-Exam Review** - AI-flagged events reviewed by humans
