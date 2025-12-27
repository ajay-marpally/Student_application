# Student Exam Application - Forensics Checklist

## Purpose

This checklist ensures evidence bundles from the Student Exam Application are court-ready and meet legal requirements for exam malpractice cases.

## Pre-Collection Verification

- [ ] Verify application version and build hash
- [ ] Check system clock was synchronized with server
- [ ] Confirm Supabase connection was active during exam
- [ ] Review audit logs for any anomalies

## Evidence Collection

### 1. Student Identification

- [ ] Hall ticket number recorded
- [ ] Student name and ID verified
- [ ] Exam center and lab noted
- [ ] System fingerprint captured

### 2. Exam Session Data

- [ ] Exam attempt ID documented
- [ ] Start time recorded (ISO 8601 with timezone)
- [ ] End time recorded
- [ ] Final status (SUBMITTED/TERMINATED)
- [ ] Duration within allowed limits

### 3. Violations Recorded

For each malpractice event:

- [ ] Event type documented
- [ ] Timestamp with milliseconds
- [ ] Severity score (1-10)
- [ ] AI confidence level
- [ ] Source confirmed as "STUDENT_AI"
- [ ] Description is human-readable

### 4. Video Evidence

For each evidence clip:

- [ ] File exists at storage URL
- [ ] SHA-256 hash matches recorded value
- [ ] File size matches recorded value
- [ ] Capture timestamp within exam period
- [ ] Video playable and clear
- [ ] Violation visible in footage

### 5. Integrity Verification

- [ ] Run `verify_export_bundle.py` script
- [ ] All SHA-256 hashes verified
- [ ] Manifest JSON is valid
- [ ] Chain of custody documented

## Export Bundle Contents

An export bundle should contain:

```
export_bundle_<attempt_id>/
├── manifest.json           # Bundle metadata
├── evidence/               # Video/image clips
│   ├── clip_001.mp4
│   ├── clip_002.mp4
│   └── ...
├── database_snapshot.json  # All related DB records
├── audit_log.json          # Complete audit trail
└── verification_report.txt # Hash verification results
```

## Manifest Required Fields

```json
{
  "version": "1.0",
  "generated_at": "ISO8601 timestamp",
  "attempt_id": "UUID",
  "student_id": "UUID",
  "exam_id": "UUID",
  "violations_count": 5,
  "evidence_files": [
    {
      "filename": "clip_001.mp4",
      "hash_sha256": "abc123...",
      "size_bytes": 1048576,
      "captured_at": "ISO8601 timestamp"
    }
  ],
  "bundle_hash": "SHA256 of all content"
}
```

## Verification Commands

```bash
# Verify individual file
sha256sum evidence/clip_001.mp4

# Verify all files against manifest
python verify_export_bundle.py export_bundle_<id>/

# Generate verification report
python verify_export_bundle.py export_bundle_<id>/ --report
```

## Legal Considerations

1. **Chain of Custody**: Document all handlers of evidence
2. **Timestamp Accuracy**: All times in UTC with timezone
3. **Evidence Integrity**: SHA-256 hashes for all files
4. **Access Control**: Limited access to evidence storage
5. **Retention Policy**: Evidence retained per legal requirements

## Review Process

1. AI flags violation automatically
2. System generates evidence bundle
3. Administrator reviews flagged videos
4. If confirmed, escalate to exam committee
5. Student notified and given right to respond
6. Final decision made by authorized body

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Evidence Collector | | | |
| Technical Verifier | | | |
| Legal Reviewer | | | |
