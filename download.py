#!/usr/bin/env python3
"""
Download Florida DBPR real estate license CSV files from FTP server.

This script downloads regional CSV files from the Florida Department of 
Business and Professional Regulation's FTP server and saves them to the 
data/raw directory.
"""

import ftplib
from pathlib import Path
from datetime import datetime
from typing import List
import time
import sys

# FTP Settings
FTP_HOST = "dbprftp.state.fl.us"
FTP_PATH = "/pub/llweb/"
FTP_TIMEOUT = 30
FTP_RETRY_ATTEMPTS = 3
FTP_RETRY_DELAY = 5


class FTPDownloader:
    """Downloads CSV files from DBPR FTP server."""
    
    # File patterns to download - RE_rgn1 through RE_rgn14
    REGIONAL_FILES = [f"RE_rgn{i}.csv" for i in range(1, 15)]
    
    def __init__(self, raw_dir: str = "data/raw"):
        """
        Initialize downloader with FTP settings.
        
        Args:
            raw_dir: Directory to save downloaded files
        """
        self.host = FTP_HOST
        self.path = FTP_PATH
        self.timeout = FTP_TIMEOUT
        self.retry_attempts = FTP_RETRY_ATTEMPTS
        self.retry_delay = FTP_RETRY_DELAY
        
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        
        print("=" * 70)
        print("FTP Downloader Initialized")
        print("=" * 70)
        print(f"FTP Host: {self.host}")
        print(f"FTP Path: {self.path}")
        print(f"Local Dir: {self.raw_dir}")
        print(f"Files to download: {len(self.REGIONAL_FILES)}")
        print()
    
    @property
    def all_files(self) -> List[str]:
        """Get list of all files to download."""
        return self.REGIONAL_FILES
    
    def connect_ftp(self) -> ftplib.FTP:
        """
        Connect to FTP server with retries.
        
        Returns:
            Connected FTP object
            
        Raises:
            Exception if connection fails after all retries
        """
        for attempt in range(1, self.retry_attempts + 1):
            try:
                print(f"Connecting to FTP server (attempt {attempt}/{self.retry_attempts})...")
                ftp = ftplib.FTP(self.host, timeout=self.timeout)
                ftp.login()  # Anonymous login
                ftp.cwd(self.path)
                print(f"✓ Connected successfully to {self.host}{self.path}")
                return ftp
            except Exception as e:
                print(f"✗ Connection attempt {attempt} failed: {e}")
                if attempt < self.retry_attempts:
                    print(f"  Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(f"Failed to connect after {self.retry_attempts} attempts")
    
    def download_file(self, ftp: ftplib.FTP, filename: str) -> bool:
        """
        Download a single file from FTP server.
        
        Args:
            ftp: Connected FTP object
            filename: Name of file to download
            
        Returns:
            True if successful, False otherwise
        """
        local_path = self.raw_dir / filename
        temp_path = self.raw_dir / f"{filename}.tmp"
        
        try:
            # Get file size for progress
            try:
                file_size = ftp.size(filename)
                size_mb = file_size / (1024 * 1024) if file_size else 0
                print(f"  Downloading {filename} ({size_mb:.2f} MB)...", end=" ", flush=True)
            except:
                print(f"  Downloading {filename}...", end=" ", flush=True)
            
            # Download to temporary file
            with open(temp_path, 'wb') as f:
                ftp.retrbinary(f'RETR {filename}', f.write)
            
            # Move to final location
            temp_path.rename(local_path)
            
            print("✓ Done")
            return True
            
        except ftplib.error_perm as e:
            print(f"✗ Failed: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False
        except Exception as e:
            print(f"✗ Error: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False
    
    def download_all(self, overwrite: bool = False) -> dict:
        """
        Download all regional CSV files.
        
        Args:
            overwrite: If True, re-download existing files
            
        Returns:
            Dictionary with download statistics
        """
        start_time = datetime.now()
        stats = {
            'total': len(self.all_files),
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'files': []
        }
        
        print("\n" + "=" * 70)
        print("Starting Download")
        print("=" * 70)
        
        try:
            # Connect to FTP
            ftp = self.connect_ftp()
            
            # Download each file
            for i, filename in enumerate(self.all_files, 1):
                print(f"\n[{i}/{stats['total']}] {filename}")
                
                local_path = self.raw_dir / filename
                
                # Check if file already exists
                if local_path.exists() and not overwrite:
                    file_size = local_path.stat().st_size / (1024 * 1024)
                    print(f"  File exists ({file_size:.2f} MB) - skipping")
                    stats['skipped'] += 1
                    stats['files'].append({
                        'name': filename,
                        'status': 'skipped',
                        'path': str(local_path)
                    })
                    continue
                
                # Download file
                success = self.download_file(ftp, filename)
                
                if success:
                    stats['downloaded'] += 1
                    file_size = local_path.stat().st_size / (1024 * 1024)
                    stats['files'].append({
                        'name': filename,
                        'status': 'downloaded',
                        'path': str(local_path),
                        'size_mb': file_size
                    })
                else:
                    stats['failed'] += 1
                    stats['files'].append({
                        'name': filename,
                        'status': 'failed',
                        'path': None
                    })
            
            # Close FTP connection
            ftp.quit()
            print("\n✓ FTP connection closed")
            
        except Exception as e:
            print(f"\n✗ Download process error: {e}")
            stats['error'] = str(e)
        
        # Calculate duration
        duration = datetime.now() - start_time
        stats['duration'] = str(duration)
        
        # Print summary
        self.print_summary(stats)
        
        return stats
    
    def print_summary(self, stats: dict):
        """Print download summary."""
        print("\n" + "=" * 70)
        print("Download Summary")
        print("=" * 70)
        print(f"Total files:      {stats['total']}")
        print(f"Downloaded:       {stats['downloaded']}")
        print(f"Skipped:          {stats['skipped']}")
        print(f"Failed:           {stats['failed']}")
        print(f"Duration:         {stats['duration']}")
        
        if stats['downloaded'] > 0:
            total_size = sum(f.get('size_mb', 0) for f in stats['files'] if f['status'] == 'downloaded')
            print(f"Total size:       {total_size:.2f} MB")
        
        print()
        
        if stats['failed'] > 0:
            print("Failed files:")
            for file_info in stats['files']:
                if file_info['status'] == 'failed':
                    print(f"  - {file_info['name']}")
            print()


def main():
    """Main execution function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Download Florida DBPR real estate license CSV files'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Re-download existing files'
    )
    parser.add_argument(
        '--dir',
        default='data/raw',
        help='Directory to save files (default: data/raw)'
    )
    
    args = parser.parse_args()
    
    # Create downloader and start download
    downloader = FTPDownloader(raw_dir=args.dir)
    
    try:
        stats = downloader.download_all(overwrite=args.overwrite)
        
        # Exit with error code if any downloads failed
        if stats['failed'] > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n✗ Download cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()