#!/usr/bin/env python3
"""
DBPR CSV Quirk Analysis Script

Analyzes CSV files to understand and quantify the data quirks discovered
from the legacy Pandas code:
1. Instructor records with duplicate license numbers
2. Private address duplicates
3. Exact duplicate rows
4. Date parsing issues
5. Whitespace issues

Usage:
    python analyze_csv_quirks.py
    python analyze_csv_quirks.py --sample 10000
    python analyze_csv_quirks.py --dir data/raw
"""

import polars as pl
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import argparse
from datetime import datetime


# Column definitions
CSV_COLUMNS = [
    'board', 'board_name', 'licensee_name', 'dba_name', 'rank_',
    'address_1', 'address_2', 'address_3', 'city', 'state', 'zip_',
    'county_code', 'county_name', 'license_number', 'primary_status',
    'secondary_status', 'original_license_date', 'status_effective_date',
    'license_expiration_date', 'alternate_license_number',
    'self_proprietors_name', 'employers_name', 'employers_license_number'
]


class QuirkAnalyzer:
    """Analyze DBPR CSV files for known data quirks."""
    
    def __init__(self, sample_size: Optional[int] = None):
        self.sample_size = sample_size
        self.stats = {
            'files_processed': 0,
            'total_rows': 0,
            'exact_duplicates': 0,
            'instructor_rows': 0,
            'license_number_duplicates': 0,
            'private_address_rows': 0,
            'private_address_duplicates': 0,
            'date_parse_errors': {},
            'whitespace_issues': 0,
        }
    
    def read_csv_files(self, filepaths: List[Path]) -> pl.DataFrame:
        """Read and combine all CSV files."""
        print("\n" + "="*80)
        print("READING CSV FILES")
        print("="*80)
        
        dfs = []
        
        for filepath in filepaths:
            print(f"\n📂 Reading {filepath.name}...", end=" ")
            
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
                
                dfs.append(df)
                print(f"{len(df):,} rows")
                self.stats['files_processed'] += 1
                
            except Exception as e:
                print(f"❌ ERROR: {e}")
                continue
        
        if not dfs:
            raise ValueError("No dataframes were successfully loaded")
        
        print(f"\n🔗 Combining {len(dfs)} dataframes...")
        combined = pl.concat(dfs, how='vertical')
        self.stats['total_rows'] = len(combined)
        
        print(f"✅ Total rows loaded: {self.stats['total_rows']:,}")
        
        return combined
    
    def analyze_exact_duplicates(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Analyze exact duplicate rows."""
        print("\n" + "="*80)
        print("QUIRK #1: EXACT DUPLICATE ROWS")
        print("="*80)
        
        print("\n📊 Analyzing exact duplicate rows...")
        
        original_count = len(df)
        unique_df = df.unique(keep='first')
        unique_count = len(unique_df)
        
        duplicates_removed = original_count - unique_count
        duplicate_pct = (duplicates_removed / original_count * 100) if original_count > 0 else 0
        
        self.stats['exact_duplicates'] = duplicates_removed
        
        print(f"\n📈 Results:")
        print(f"   Original rows:        {original_count:,}")
        print(f"   Unique rows:          {unique_count:,}")
        print(f"   Exact duplicates:     {duplicates_removed:,} ({duplicate_pct:.2f}%)")
        
        if duplicates_removed > 0:
            print(f"\n⚠️  IMPACT: {duplicates_removed:,} rows would be removed by drop_duplicates()")
        else:
            print(f"\n✅ No exact duplicates found")
        
        return {
            'original_count': original_count,
            'unique_count': unique_count,
            'duplicates_removed': duplicates_removed,
            'duplicate_pct': duplicate_pct
        }
    
    def analyze_instructor_duplicates(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Analyze instructor records with duplicate license numbers."""
        print("\n" + "="*80)
        print("QUIRK #2: INSTRUCTOR DUPLICATE LICENSE NUMBERS")
        print("="*80)
        
        print("\n🎓 Analyzing instructor records (rank starts with 'Z')...")
        
        # Count instructor rows
        instructor_df = df.filter(pl.col('rank_').str.starts_with('Z'))
        instructor_count = len(instructor_df)
        instructor_pct = (instructor_count / len(df) * 100) if len(df) > 0 else 0
        
        self.stats['instructor_rows'] = instructor_count
        
        print(f"\n📊 Instructor Records:")
        print(f"   Total instructors:    {instructor_count:,} ({instructor_pct:.2f}%)")
        
        # Show breakdown by rank
        if instructor_count > 0:
            print(f"\n   Breakdown by rank:")
            rank_counts = instructor_df.group_by('rank_').agg(
                pl.count().alias('count')
            ).sort('count', descending=True)
            
            for row in rank_counts.iter_rows(named=True):
                rank = row['rank_']
                count = row['count']
                pct = (count / instructor_count * 100)
                print(f"      {rank:25s}: {count:6,} ({pct:5.1f}%)")
        
        # Check for duplicate license numbers among instructors
        instructor_licenses = instructor_df.select('license_number').unique()
        
        # Find license numbers that appear in both instructor and non-instructor records
        non_instructor_df = df.filter(~pl.col('rank_').str.starts_with('Z'))
        non_instructor_licenses = non_instructor_df.select('license_number').unique()
        
        # Find overlapping license numbers
        overlapping = instructor_licenses.join(
            non_instructor_licenses,
            on='license_number',
            how='inner'
        )
        
        overlap_count = len(overlapping)
        
        print(f"\n🔍 Duplicate License Number Analysis:")
        print(f"   Instructor licenses:        {len(instructor_licenses):,}")
        print(f"   Non-instructor licenses:    {len(non_instructor_licenses):,}")
        print(f"   Overlapping licenses:       {overlap_count:,}")
        
        if overlap_count > 0:
            print(f"\n⚠️  CRITICAL: {overlap_count:,} license numbers appear in BOTH instructor and non-instructor records!")
            print(f"   This is WHY legacy code filters out instructors!")
            
            # Show examples
            print(f"\n   Sample overlapping license numbers:")
            examples = overlapping.head(10)
            for lic_num in examples['license_number'].to_list():
                # Get both records
                both = df.filter(pl.col('license_number') == lic_num).select(['license_number', 'rank_', 'licensee_name'])
                print(f"\n   License {lic_num}:")
                for row in both.iter_rows(named=True):
                    print(f"      {row['rank_']:25s} - {row['licensee_name']}")
        else:
            print(f"\n✅ No overlapping license numbers between instructors and non-instructors")
        
        return {
            'instructor_count': instructor_count,
            'instructor_pct': instructor_pct,
            'overlapping_licenses': overlap_count,
            'would_filter': instructor_count
        }
    
    def analyze_private_addresses(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Analyze private address markers and their impact on duplicates."""
        print("\n" + "="*80)
        print("QUIRK #3: PRIVATE ADDRESS DUPLICATES")
        print("="*80)
        
        print("\n🏠 Analyzing private address markers...")
        
        # Count rows with private addresses
        private_df = df.filter(
            pl.col('address_1').str.starts_with('**Private')
        )
        private_count = len(private_df)
        private_pct = (private_count / len(df) * 100) if len(df) > 0 else 0
        
        self.stats['private_address_rows'] = private_count
        
        print(f"\n📊 Private Address Markers:")
        print(f"   Rows with '**Private': {private_count:,} ({private_pct:.2f}%)")
        
        if private_count > 0:
            print(f"\n   Sample private address values:")
            samples = private_df.select(['address_1', 'licensee_name']).head(5)
            for row in samples.iter_rows(named=True):
                print(f"      '{row['address_1'][:50]}' - {row['licensee_name']}")
        
        # Now check: After filtering instructors, how many duplicates have private addresses?
        print(f"\n🔍 Analyzing duplicate handling (after filtering instructors)...")
        
        # Filter out instructors first (matching legacy behavior)
        non_instructor_df = df.filter(~pl.col('rank_').str.starts_with('Z'))
        
        # Find duplicate license numbers
        duplicate_licenses = (
            non_instructor_df.group_by('license_number')
            .agg(pl.count().alias('count'))
            .filter(pl.col('count') > 1)
        )
        
        duplicate_count = len(duplicate_licenses)
        
        print(f"   License numbers with duplicates: {duplicate_count:,}")
        
        if duplicate_count > 0:
            # For each duplicate set, check if private address is involved
            duplicate_with_private = 0
            total_duplicate_rows = 0
            
            for lic_num in duplicate_licenses['license_number'].to_list()[:100]:  # Sample first 100
                dupes = non_instructor_df.filter(pl.col('license_number') == lic_num)
                total_duplicate_rows += len(dupes)
                
                has_private = dupes.filter(
                    pl.col('address_1').str.starts_with('**Private')
                ).height > 0
                
                if has_private:
                    duplicate_with_private += 1
            
            private_dup_pct = (duplicate_with_private / min(100, duplicate_count) * 100)
            
            self.stats['private_address_duplicates'] = duplicate_with_private
            
            print(f"\n   Duplicate sets analyzed: {min(100, duplicate_count)}")
            print(f"   Sets with private address: {duplicate_with_private} ({private_dup_pct:.1f}%)")
            print(f"   Total rows in duplicate sets: {total_duplicate_rows:,}")
            
            if duplicate_with_private > 0:
                print(f"\n⚠️  IMPACT: Private address handler would affect {duplicate_with_private} duplicate sets")
                
                # Show an example
                print(f"\n   Example duplicate set with private address:")
                example_lic = None
                for lic_num in duplicate_licenses['license_number'].to_list():
                    dupes = non_instructor_df.filter(pl.col('license_number') == lic_num)
                    has_private = dupes.filter(
                        pl.col('address_1').str.starts_with('**Private')
                    ).height > 0
                    if has_private:
                        example_lic = lic_num
                        break
                
                if example_lic:
                    example_dupes = non_instructor_df.filter(
                        pl.col('license_number') == example_lic
                    ).select(['license_number', 'licensee_name', 'address_1', 'rank_'])
                    
                    print(f"\n   License {example_lic}:")
                    for row in example_dupes.iter_rows(named=True):
                        addr = row['address_1'][:40] if row['address_1'] else 'NULL'
                        print(f"      {row['rank_']:25s} | {addr:40s} | {row['licensee_name']}")
        else:
            print(f"\n✅ No duplicate license numbers after filtering instructors")
        
        return {
            'private_count': private_count,
            'private_pct': private_pct,
            'duplicates_after_instructor_filter': duplicate_count,
            'duplicates_with_private': duplicate_with_private if duplicate_count > 0 else 0
        }
    
    def analyze_date_parsing(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Analyze date parsing issues."""
        print("\n" + "="*80)
        print("QUIRK #4: DATE PARSING ERRORS")
        print("="*80)
        
        print("\n📅 Analyzing date fields...")
        
        date_cols = ['original_license_date', 'status_effective_date', 'license_expiration_date']
        results = {}
        
        for col in date_cols:
            print(f"\n   {col}:")
            
            # Count nulls
            null_count = df.filter(pl.col(col).is_null()).height
            null_pct = (null_count / len(df) * 100) if len(df) > 0 else 0
            
            print(f"      Null values:        {null_count:,} ({null_pct:.2f}%)")
            
            # Try parsing with coerce
            parsed = df.with_columns([
                pl.col(col).str.to_date('%m/%d/%Y', strict=False).alias(f'{col}_parsed')
            ])
            
            # Count parse failures (nulls after parsing that weren't null before)
            parse_failures = parsed.filter(
                (pl.col(col).is_not_null()) & 
                (pl.col(f'{col}_parsed').is_null())
            ).height
            
            parse_fail_pct = (parse_failures / len(df) * 100) if len(df) > 0 else 0
            
            print(f"      Parse failures:     {parse_failures:,} ({parse_fail_pct:.2f}%)")
            
            if parse_failures > 0:
                # Show examples of unparseable dates
                examples = parsed.filter(
                    (pl.col(col).is_not_null()) & 
                    (pl.col(f'{col}_parsed').is_null())
                ).select(col).head(5)
                
                print(f"      Example bad dates:")
                for val in examples[col].to_list():
                    print(f"         '{val}'")
            
            # Check for dates successfully parsed
            success_count = parsed.filter(pl.col(f'{col}_parsed').is_not_null()).height
            success_pct = (success_count / len(df) * 100) if len(df) > 0 else 0
            
            print(f"      Successfully parsed: {success_count:,} ({success_pct:.2f}%)")
            
            results[col] = {
                'null_count': null_count,
                'parse_failures': parse_failures,
                'success_count': success_count
            }
            
            self.stats['date_parse_errors'][col] = parse_failures
        
        # Check for required date fields
        print(f"\n🔍 Checking required date fields (original_license_date, status_effective_date):")
        
        missing_required = df.filter(
            (pl.col('original_license_date').is_null()) |
            (pl.col('status_effective_date').is_null())
        ).height
        
        missing_pct = (missing_required / len(df) * 100) if len(df) > 0 else 0
        
        print(f"   Rows with missing required dates: {missing_required:,} ({missing_pct:.2f}%)")
        
        if missing_required > 0:
            print(f"\n⚠️  DECISION POINT: Should we filter these out (stricter) or keep them (legacy)?")
            print(f"   Legacy: Kept these rows with null dates")
            print(f"   Proposed: Filter them out for data quality")
        
        return results
    
    def analyze_whitespace(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Analyze whitespace issues in string fields."""
        print("\n" + "="*80)
        print("QUIRK #5: WHITESPACE ISSUES")
        print("="*80)
        
        print("\n📝 Analyzing whitespace in string fields...")
        
        string_cols = [
            'licensee_name', 'dba_name', 'address_1', 'city', 
            'state', 'county_name', 'primary_status'
        ]
        
        total_with_whitespace = 0
        
        for col in string_cols:
            # Check for leading/trailing whitespace
            with_whitespace = df.filter(
                (pl.col(col).is_not_null()) &
                (pl.col(col) != pl.col(col).str.strip_chars())
            ).height
            
            if with_whitespace > 0:
                total_with_whitespace += with_whitespace
                ws_pct = (with_whitespace / len(df) * 100)
                
                print(f"\n   {col}:")
                print(f"      Rows with leading/trailing spaces: {with_whitespace:,} ({ws_pct:.2f}%)")
                
                # Show examples
                examples = df.filter(
                    (pl.col(col).is_not_null()) &
                    (pl.col(col) != pl.col(col).str.strip_chars())
                ).select(col).head(3)
                
                print(f"      Examples:")
                for val in examples[col].to_list():
                    print(f"         '{val}' → '{val.strip()}'")
        
        self.stats['whitespace_issues'] = total_with_whitespace
        
        if total_with_whitespace > 0:
            print(f"\n⚠️  IMPACT: {total_with_whitespace:,} field values need whitespace stripping")
        else:
            print(f"\n✅ No whitespace issues found")
        
        return {'total_with_whitespace': total_with_whitespace}
    
    def print_summary(self):
        """Print comprehensive summary of all quirks."""
        print("\n" + "="*80)
        print("COMPREHENSIVE QUIRK SUMMARY")
        print("="*80)
        
        print(f"\n📊 Dataset Overview:")
        print(f"   Files processed:      {self.stats['files_processed']}")
        print(f"   Total rows:           {self.stats['total_rows']:,}")
        
        print(f"\n🔍 Data Quality Issues Found:")
        
        print(f"\n   1️⃣  Exact Duplicates:")
        print(f"      Rows to remove:   {self.stats['exact_duplicates']:,}")
        print(f"      Impact:           {(self.stats['exact_duplicates']/self.stats['total_rows']*100):.2f}% of data")
        
        print(f"\n   2️⃣  Instructor Duplicates:")
        print(f"      Instructor rows:  {self.stats['instructor_rows']:,}")
        print(f"      To filter out:    {self.stats['instructor_rows']:,}")
        print(f"      Impact:           {(self.stats['instructor_rows']/self.stats['total_rows']*100):.2f}% of data")
        
        print(f"\n   3️⃣  Private Address Duplicates:")
        print(f"      Private addresses: {self.stats['private_address_rows']:,}")
        print(f"      Affected dupes:    {self.stats['private_address_duplicates']}")
        print(f"      Impact:           Complex deduplication needed")
        
        print(f"\n   4️⃣  Date Parsing Errors:")
        total_date_errors = sum(self.stats['date_parse_errors'].values())
        print(f"      Total parse errors: {total_date_errors:,}")
        for col, count in self.stats['date_parse_errors'].items():
            if count > 0:
                print(f"         {col}: {count:,}")
        
        print(f"\n   5️⃣  Whitespace Issues:")
        print(f"      Fields affected:   {self.stats['whitespace_issues']:,}")
        
        # Calculate final expected row count after all filters
        final_count = self.stats['total_rows']
        final_count -= self.stats['exact_duplicates']
        final_count -= self.stats['instructor_rows']
        # Note: private address handler doesn't remove rows, just picks the right one
        
        print(f"\n📈 Expected Final Dataset:")
        print(f"   After exact deduplication:     {self.stats['total_rows'] - self.stats['exact_duplicates']:,}")
        print(f"   After instructor filter:       {final_count:,}")
        print(f"   After private addr handling:   {final_count:,} (same, just picks right record)")
        print(f"   Final expected row count:      {final_count:,}")
        print(f"   Reduction:                     {(self.stats['total_rows'] - final_count):,} rows ({((self.stats['total_rows'] - final_count)/self.stats['total_rows']*100):.2f}%)")
        
        print(f"\n💡 Recommendations:")
        print(f"   ✅ Strip whitespace from all fields (already planned)")
        print(f"   ✅ Remove exact duplicates with keep='first' (already planned)")
        print(f"   ⚠️  ADD: Filter out instructor records (rank starts with 'Z')")
        print(f"   ⚠️  ADD: Private address duplicate handler")
        print(f"   ⚠️  DECIDE: Keep or filter rows with null required dates")
        
        print("\n" + "="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze DBPR CSV files for data quirks"
    )
    parser.add_argument(
        '--dir',
        type=Path,
        default=Path('data/raw'),
        help='Directory containing CSV files (default: data/raw)'
    )
    parser.add_argument(
        '--sample',
        type=int,
        help='Sample size per file (default: use all records)'
    )
    
    args = parser.parse_args()
    
    # Find CSV files
    csv_files = sorted(args.dir.glob('RE_rgn*.csv'))
    
    if not csv_files:
        print(f"❌ No CSV files found in {args.dir}")
        print("Please download files first: python cli.py download")
        return 1
    
    print("\n" + "="*80)
    print("DBPR CSV QUIRK ANALYSIS")
    print("="*80)
    print(f"\nAnalyzing {len(csv_files)} CSV files from {args.dir}")
    if args.sample:
        print(f"Sampling {args.sample:,} rows per file")
    
    # Initialize analyzer
    analyzer = QuirkAnalyzer(sample_size=args.sample)
    
    # Read all CSV files
    df = analyzer.read_csv_files(csv_files)
    
    # Run all analyses
    analyzer.analyze_exact_duplicates(df)
    analyzer.analyze_instructor_duplicates(df)
    analyzer.analyze_private_addresses(df)
    analyzer.analyze_date_parsing(df)
    analyzer.analyze_whitespace(df)
    
    # Print comprehensive summary
    analyzer.print_summary()
    
    return 0


if __name__ == '__main__':
    exit(main())