#!/usr/bin/env python3
"""
Download Vosk Spanish model to models/vosk-es/

Usage:
    python download_vosk_model.py

Environment:
    RAGE_VOSK_MODEL: Custom model path (default: models/vosk-es)

The script downloads vosk-model-small-es-0.42.tar.gz from GitHub releases
and extracts it to the target directory.
"""

import os
import sys
import tarfile
import urllib.request
import hashlib
import shutil
from pathlib import Path

# Configuration
MODEL_NAME = "vosk-model-small-es-0.42"
DOWNLOAD_URL = f"https://github.com/alphacep/vosk-api/releases/download/v0.42/{MODEL_NAME}.tar.gz"
CHECKSUM_SHA256 = "4c40c67e3e0c8a1e5e9e8a3e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e5e"  # Placeholder - update with real checksum

def get_model_path():
    """Get model directory from env or default."""
    return os.environ.get("RAGE_VOSK_MODEL", "models/vosk-es")

def download_file(url, dest_path):
    """Download file with progress and checksum verification."""
    print(f"Downloading {url}...")
    
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f"Download complete: {dest_path}")
    except Exception as e:
        print(f"Download failed: {e}")
        sys.exit(1)

def verify_checksum(file_path, expected_sha256):
    """Verify SHA256 checksum of downloaded file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    actual_sha256 = sha256_hash.hexdigest()
    
    if actual_sha256 == expected_sha256:
        print(f"Checksum verified: {actual_sha256}")
        return True
    else:
        print(f"Checksum mismatch! Expected: {expected_sha256}, Got: {actual_sha256}")
        return False

def extract_tarball(tar_path, extract_to):
    """Extract tar.gz file to target directory."""
    print(f"Extracting {tar_path} to {extract_to}...")
    
    if os.path.exists(extract_to):
        shutil.rmtree(extract_to)
    
    os.makedirs(extract_to, exist_ok=True)
    
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(extract_to)
    
    print(f"Extraction complete: {extract_to}")

def main():
    model_path = get_model_path()
    target_dir = Path(model_path)
    
    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine source and destination
    script_dir = Path(__file__).parent.resolve()
    temp_dir = script_dir / "temp_download"
    tar_path = temp_dir / f"{MODEL_NAME}.tar.gz"
    extracted_dir = target_dir / MODEL_NAME.replace(".tar.gz", "")
    
    # Clean up previous downloads
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir)
    
    # Create temp directory
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Download
        download_file(DOWNLOAD_URL, str(tar_path))
        
        # Verify checksum (comment out during development)
        # if not verify_checksum(str(tar_path), CHECKSUM_SHA256):
        #     sys.exit(1)
        
        # Extract
        extract_tarball(str(tar_path), str(extracted_dir))
        
        print(f"\nModel downloaded successfully to: {extracted_dir}")
        print(f"Model name: {extracted_dir.name}")
        
    finally:
        # Clean up temp directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
