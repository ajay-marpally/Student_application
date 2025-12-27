#!/usr/bin/env python3
"""
Verify Export Bundle - Evidence integrity verification script.

Usage:
    python verify_export_bundle.py <bundle_path> [--report]
    
This script verifies SHA-256 hashes of all evidence files in an export bundle.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime


def compute_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def verify_bundle(bundle_path: Path, generate_report: bool = False) -> bool:
    """
    Verify integrity of an export bundle.
    
    Args:
        bundle_path: Path to the bundle directory
        generate_report: Whether to write a verification report
        
    Returns:
        True if all files verify successfully
    """
    print(f"Verifying bundle: {bundle_path}")
    print("=" * 60)
    
    # Load manifest
    manifest_path = bundle_path / "manifest.json"
    
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found at {manifest_path}")
        return False
    
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    print(f"Bundle version: {manifest.get('version', 'unknown')}")
    print(f"Generated at: {manifest.get('generated_at', 'unknown')}")
    print(f"Attempt ID: {manifest.get('attempt_id', 'unknown')}")
    print()
    
    # Verify each evidence file
    evidence_files = manifest.get("evidence_files", [])
    
    if not evidence_files:
        print("WARNING: No evidence files in manifest")
    
    passed = 0
    failed = 0
    results = []
    
    for file_info in evidence_files:
        filename = file_info["filename"]
        expected_hash = file_info["hash_sha256"]
        expected_size = file_info.get("size_bytes")
        
        file_path = bundle_path / "evidence" / filename
        
        if not file_path.exists():
            print(f"FAIL: {filename} - File not found")
            failed += 1
            results.append({
                "file": filename,
                "status": "NOT_FOUND",
                "error": "File does not exist"
            })
            continue
        
        # Check size
        actual_size = file_path.stat().st_size
        if expected_size and actual_size != expected_size:
            print(f"FAIL: {filename} - Size mismatch (expected {expected_size}, got {actual_size})")
            failed += 1
            results.append({
                "file": filename,
                "status": "SIZE_MISMATCH",
                "expected_size": expected_size,
                "actual_size": actual_size
            })
            continue
        
        # Check hash
        actual_hash = compute_hash(file_path)
        
        if actual_hash.lower() == expected_hash.lower():
            print(f"PASS: {filename}")
            passed += 1
            results.append({
                "file": filename,
                "status": "VERIFIED",
                "hash": actual_hash
            })
        else:
            print(f"FAIL: {filename} - Hash mismatch")
            print(f"       Expected: {expected_hash}")
            print(f"       Actual:   {actual_hash}")
            failed += 1
            results.append({
                "file": filename,
                "status": "HASH_MISMATCH",
                "expected_hash": expected_hash,
                "actual_hash": actual_hash
            })
    
    # Summary
    print()
    print("=" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    
    overall_status = "VERIFIED" if failed == 0 else "FAILED"
    print(f"OVERALL STATUS: {overall_status}")
    
    # Generate report if requested
    if generate_report:
        report = {
            "verification_time": datetime.now().isoformat(),
            "bundle_path": str(bundle_path),
            "manifest_version": manifest.get("version"),
            "attempt_id": manifest.get("attempt_id"),
            "total_files": len(evidence_files),
            "passed": passed,
            "failed": failed,
            "overall_status": overall_status,
            "results": results
        }
        
        report_path = bundle_path / "verification_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nReport saved to: {report_path}")
    
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Verify export bundle integrity")
    parser.add_argument("bundle_path", help="Path to the export bundle directory")
    parser.add_argument("--report", action="store_true", help="Generate verification report")
    
    args = parser.parse_args()
    
    bundle_path = Path(args.bundle_path)
    
    if not bundle_path.exists():
        print(f"ERROR: Bundle path does not exist: {bundle_path}")
        sys.exit(1)
    
    success = verify_bundle(bundle_path, args.report)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
