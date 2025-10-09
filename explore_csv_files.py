#!/usr/bin/env python3
"""
DBPR CSV Data Exploration Script

Analyzes CSV files to identify:
- Missing/null values
- String length extremes
- Data type inconsistencies
- Unusual patterns
- Potential data quality issues

Usage:
    python explore_csvs.py
    python explore_csvs.py --files data/raw/RE_rgn1.csv data/raw/RE_rgn2.csv
    python explore_csvs.py --sample 10000  # Only analyze first 10k rows
"""

import polars as pl
from pathlib import Path
from typing import List, Dict, Any
import argparse
from collections import Counter
import re


# Column definitions (from your schema)
CSV_COLUMNS = [
    'board', 'board_name', 'licensee_name', 'dba_name', 'rank_',
    'address_1', 'address_2', 'address_3', 'city', 'state', 'zip_',
    'county_code', 'county_name', 'license_number', 'primary_status',
    'secondary_status', 'original_license_date', 'status_effective_date',
    'license_expiration_date', 'alternate_license_number',
    'self_proprietors_name', 'employers_name', 'employers_license_number'
]


class CSVExplorer:
    """Explore and analyze DBPR CSV files for data quality issues."""
    
    def __init__(self, sample_size: int = None):
        self.sample_size = sample_size
        self.issues = []
    
    def read_csv(self, filepath: Path) -> pl.DataFrame:
        """Read CSV with error handling."""
        print(f"\n{'='*60}")
        print(f"Reading: {filepath.name}")
        print('='*60)
        
        try:
            df = pl.read_csv(
                filepath,
                has_header=False,
                new_columns=CSV_COLUMNS,
                encoding='utf8-lossy',
                ignore_errors=True,
                truncate_ragged_lines=True,
                dtypes={col: pl.Utf8 for col in CSV_COLUMNS},
                n_rows=self.sample_size
            )
            
            print(f"✓ Successfully read {len(df):,} rows")
            return df
        
        except Exception as e:
            print(f"✗ Failed to read {filepath.name}: {e}")
            return None
    
    def analyze_nulls(self, df: pl.DataFrame, filename: str):
        """Analyze missing/null values."""
        print("\n--- NULL VALUE ANALYSIS ---")
        
        null_counts = {}
        for col in df.columns:
            # Count empty strings and actual nulls
            null_count = df.filter(
                (pl.col(col).is_null()) | (pl.col(col) == '')
            ).height
            
            if null_count > 0:
                null_pct = (null_count / len(df)) * 100
                null_counts[col] = (null_count, null_pct)
        
        if null_counts:
            print(f"\nColumns with missing data (total rows: {len(df):,}):")
            for col, (count, pct) in sorted(null_counts.items(), key=lambda x: x[1][0], reverse=True):
                print(f"  {col:30s}: {count:6,} ({pct:5.1f}%)")
                
                # Flag critical fields with nulls
                if col in ['license_number', 'licensee_name', 'original_license_date'] and count > 0:
                    self.issues.append(f"{filename}: CRITICAL - {col} has {count} nulls!")
        else:
            print("✓ No null values found")
    
    def analyze_string_lengths(self, df: pl.DataFrame, filename: str):
        """Analyze string field lengths to identify outliers."""
        print("\n--- STRING LENGTH ANALYSIS ---")
        
        string_cols = [
            'licensee_name', 'dba_name', 'address_1', 'address_2', 'address_3',
            'city', 'self_proprietors_name', 'employers_name'
        ]
        
        for col in string_cols:
            if col not in df.columns:
                continue
            
            # Filter out nulls and empty strings
            non_null = df.filter(
                (pl.col(col).is_not_null()) & (pl.col(col) != '')
            )
            
            if len(non_null) == 0:
                continue
            
            lengths = non_null.select(pl.col(col).str.len_chars().alias('length'))
            
            min_len = lengths['length'].min()
            max_len = lengths['length'].max()
            avg_len = lengths['length'].mean()
            
            print(f"\n{col}:")
            print(f"  Length range: {min_len} - {max_len} chars (avg: {avg_len:.1f})")
            
            # Show examples of longest values
            if max_len > 50:
                longest = non_null.sort(pl.col(col).str.len_chars(), descending=True).head(3)
                print(f"  Longest examples ({max_len} chars):")
                for val in longest[col].to_list():
                    print(f"    '{val[:70]}...'") if len(val) > 70 else print(f"    '{val}'")
            
            # Flag suspiciously long values
            if col == 'licensee_name' and max_len > 64:
                self.issues.append(f"{filename}: {col} exceeds 64 chars (max: {max_len})")
            if col in ['address_1', 'address_2', 'address_3'] and max_len > 64:
                self.issues.append(f"{filename}: {col} exceeds 64 chars (max: {max_len})")
    
    def analyze_license_numbers(self, df: pl.DataFrame, filename: str):
        """Analyze license numbers for patterns and issues."""
        print("\n--- LICENSE NUMBER ANALYSIS ---")
        
        # Check for nulls
        nulls = df.filter(pl.col('license_number').is_null()).height
        if nulls > 0:
            print(f"⚠ Found {nulls} null license numbers!")
            self.issues.append(f"{filename}: {nulls} null license numbers")
        
        # Check for duplicates
        unique_count = df['license_number'].n_unique()
        total_count = len(df)
        duplicates = total_count - unique_count
        
        if duplicates > 0:
            print(f"⚠ Found {duplicates} duplicate license numbers!")
            self.issues.append(f"{filename}: {duplicates} duplicate license numbers")
            
            # Show examples
            dupe_df = df.group_by('license_number').agg(pl.count().alias('count')).filter(pl.col('count') > 1)
            print(f"  Example duplicates: {dupe_df.head(5)['license_number'].to_list()}")
        else:
            print(f"✓ All {total_count:,} license numbers are unique")
        
        # Check for leading zeroes (should be none if INTEGER)
        leading_zero = df.filter(
            (pl.col('license_number').is_not_null()) & 
            (pl.col('license_number').str.starts_with('0'))
        ).height
        
        if leading_zero > 0:
            print(f"⚠ Found {leading_zero} license numbers with leading zeroes")
            examples = df.filter(pl.col('license_number').str.starts_with('0')).head(5)['license_number'].to_list()
            print(f"  Examples: {examples}")
            self.issues.append(f"{filename}: {leading_zero} license numbers with leading zeroes")
        
        # Check length distribution
        lengths = df.filter(
            pl.col('license_number').is_not_null()
        ).select(pl.col('license_number').str.len_chars().alias('length'))
        
        length_counts = lengths.group_by('length').agg(pl.count().alias('count')).sort('length')
        
        print("\nLicense number length distribution:")
        for row in length_counts.iter_rows():
            length, count = row
            pct = (count / len(df)) * 100
            print(f"  {length} digits: {count:7,} ({pct:5.1f}%)")
        
        # Check for non-numeric characters
        non_numeric = df.filter(
            (pl.col('license_number').is_not_null()) & 
            (~pl.col('license_number').str.contains(r'^\d+$'))
        ).height
        
        if non_numeric > 0:
            print(f"⚠ Found {non_numeric} non-numeric license numbers")
            examples = df.filter(
                (pl.col('license_number').is_not_null()) & 
                (~pl.col('license_number').str.contains(r'^\d+$'))
            ).head(5)['license_number'].to_list()
            print(f"  Examples: {examples}")
            self.issues.append(f"{filename}: {non_numeric} non-numeric license numbers")
    
    def analyze_dates(self, df: pl.DataFrame, filename: str):
        """Analyze date fields for format issues."""
        print("\n--- DATE ANALYSIS ---")
        
        date_cols = ['original_license_date', 'status_effective_date', 'license_expiration_date']
        date_format = r'^\d{2}/\d{2}/\d{4}$'
        
        for col in date_cols:
            non_null = df.filter(pl.col(col).is_not_null())
            
            if len(non_null) == 0:
                print(f"\n{col}: All null")
                continue
            
            # Check format
            valid_format = non_null.filter(pl.col(col).str.contains(date_format)).height
            invalid_format = len(non_null) - valid_format
            
            print(f"\n{col}:")
            print(f"  Valid format (MM/DD/YYYY): {valid_format:,}")
            
            if invalid_format > 0:
                print(f"  ⚠ Invalid format: {invalid_format}")
                examples = non_null.filter(~pl.col(col).str.contains(date_format)).head(5)[col].to_list()
                print(f"    Examples: {examples}")
                self.issues.append(f"{filename}: {col} has {invalid_format} invalid date formats")
            
            # Try parsing and show min/max
            try:
                parsed = non_null.with_columns(
                    pl.col(col).str.to_date('%m/%d/%Y', strict=False).alias(f'{col}_parsed')
                )
                
                min_date = parsed[f'{col}_parsed'].min()
                max_date = parsed[f'{col}_parsed'].max()
                
                print(f"  Date range: {min_date} to {max_date}")
                
                # Check for suspicious dates
                if min_date and min_date.year < 1900:
                    self.issues.append(f"{filename}: {col} has dates before 1900")
                
            except Exception as e:
                print(f"  ⚠ Could not parse dates: {e}")
    
    def analyze_enums(self, df: pl.DataFrame, filename: str):
        """Analyze enumeration fields for unexpected values."""
        print("\n--- ENUMERATION ANALYSIS ---")
        
        # Primary Status
        print("\nPrimary Status values:")
        status_counts = df.group_by('primary_status').agg(pl.count().alias('count')).sort('count', descending=True)
        for row in status_counts.iter_rows():
            status, count = row
            pct = (count / len(df)) * 100
            print(f"  {status:20s}: {count:7,} ({pct:5.1f}%)")
        
        expected_statuses = ['Probation', 'Current', 'Suspended', 'Delinquent', 'Invol Inactive']
        actual_statuses = set(df['primary_status'].unique().to_list())
        unexpected = actual_statuses - set(expected_statuses) - {None, ''}
        
        if unexpected:
            print(f"  ⚠ Unexpected statuses: {unexpected}")
            self.issues.append(f"{filename}: Unexpected primary statuses: {unexpected}")
        
        # Secondary Status
        print("\nSecondary Status values:")
        sec_status_counts = df.group_by('secondary_status').agg(pl.count().alias('count')).sort('count', descending=True)
        for row in sec_status_counts.iter_rows():
            status, count = row
            pct = (count / len(df)) * 100
            status_str = str(status) if status else 'NULL/Empty'
            print(f"  {status_str:20s}: {count:7,} ({pct:5.1f}%)")
        
        # Rank
        print("\nRank values:")
        rank_counts = df.group_by('rank_').agg(pl.count().alias('count')).sort('count', descending=True)
        for row in rank_counts.iter_rows():
            rank, count = row
            pct = (count / len(df)) * 100
            print(f"  {rank:25s}: {count:7,} ({pct:5.1f}%)")
        
        expected_ranks = [
            'BK Broker', 'BL Broker Sales', 'BO RE Branch Offic', 'CQ RE Corp.',
            'PR RE Partnership', 'SL Sales Associate', 'ZH RE Instructor', 'ZH Add Sch Loc'
        ]
        actual_ranks = set(df['rank_'].unique().to_list())
        unexpected_ranks = actual_ranks - set(expected_ranks) - {None, ''}
        
        if unexpected_ranks:
            print(f"  ⚠ Unexpected ranks: {unexpected_ranks}")
            self.issues.append(f"{filename}: Unexpected ranks: {unexpected_ranks}")
        
        # State codes
        print("\nTop 10 State codes:")
        state_counts = df.group_by('state').agg(pl.count().alias('count')).sort('count', descending=True).head(10)
        for row in state_counts.iter_rows():
            state, count = row
            pct = (count / len(df)) * 100
            print(f"  {state:5s}: {count:7,} ({pct:5.1f}%)")
    
    def analyze_city_names(self, df: pl.DataFrame, filename: str):
        """Analyze city name variations."""
        print("\n--- CITY NAME ANALYSIS ---")
        
        unique_cities = df['city'].n_unique()
        print(f"Unique city values: {unique_cities:,}")
        
        # Show most common cities
        print("\nTop 20 cities:")
        city_counts = df.group_by('city').agg(pl.count().alias('count')).sort('count', descending=True).head(20)
        for row in city_counts.iter_rows():
            city, count = row
            pct = (count / len(df)) * 100
            city_str = str(city)[:30] if city else 'NULL/Empty'
            print(f"  {city_str:30s}: {count:7,} ({pct:5.1f}%)")
        
        # Look for variations that might need normalization
        print("\nLooking for city name variations...")
        cities = df['city'].unique().drop_nulls().to_list()
        
        # Check for common issues
        variations = {
            'case_variations': [],
            'spacing_issues': [],
            'abbreviations': []
        }
        
        seen = set()
        for city in cities:
            city_lower = city.lower() if city else ''
            
            # Check for case variations
            if city_lower in seen:
                variations['case_variations'].append(city)
            seen.add(city_lower)
            
            # Check for multiple spaces
            if '  ' in city:
                variations['spacing_issues'].append(city)
            
            # Check for abbreviations
            if 'ST ' in city or ' ST' in city:
                variations['abbreviations'].append(city)
        
        for var_type, examples in variations.items():
            if examples:
                print(f"\n{var_type.replace('_', ' ').title()} ({len(examples)} found):")
                for ex in examples[:5]:
                    print(f"  '{ex}'")
                
                if len(examples) > 5:
                    print(f"  ... and {len(examples) - 5} more")
    
    def print_summary(self):
        """Print summary of all issues found."""
        print("\n" + "="*60)
        print("SUMMARY OF ISSUES")
        print("="*60)
        
        if not self.issues:
            print("✓ No critical issues found!")
        else:
            print(f"Found {len(self.issues)} issues:\n")
            for i, issue in enumerate(self.issues, 1):
                print(f"{i}. {issue}")
    
    def explore_file(self, filepath: Path):
        """Run all analyses on a single file."""
        df = self.read_csv(filepath)
        
        if df is None:
            return
        
        self.analyze_nulls(df, filepath.name)
        self.analyze_license_numbers(df, filepath.name)
        self.analyze_string_lengths(df, filepath.name)
        self.analyze_dates(df, filepath.name)
        self.analyze_enums(df, filepath.name)
        self.analyze_city_names(df, filepath.name)
    
    def explore_files(self, filepaths: List[Path]):
        """Run analyses on multiple files."""
        for filepath in filepaths:
            self.explore_file(filepath)
        
        self.print_summary()


def main():
    parser = argparse.ArgumentParser(
        description="Explore DBPR CSV files for data quality issues"
    )
    parser.add_argument(
        '--files',
        nargs='+',
        type=Path,
        help='Specific CSV files to analyze'
    )
    parser.add_argument(
        '--sample',
        type=int,
        help='Only analyze first N rows of each file'
    )
    parser.add_argument(
        '--dir',
        type=Path,
        default=Path('data/raw'),
        help='Directory containing CSV files (default: data/raw)'
    )
    
    args = parser.parse_args()
    
    # Determine which files to analyze
    if args.files:
        filepaths = args.files
    else:
        # Find all RE_rgn*.csv files
        filepaths = sorted(args.dir.glob('RE_rgn*.csv'))
        
        if not filepaths:
            print(f"No CSV files found in {args.dir}")
            print("Please download files first or specify --files")
            return 1
    
    print(f"Analyzing {len(filepaths)} CSV file(s)...")
    if args.sample:
        print(f"(Sampling first {args.sample:,} rows from each file)")
    
    explorer = CSVExplorer(sample_size=args.sample)
    explorer.explore_files(filepaths)
    
    return 0


if __name__ == '__main__':
    exit(main())