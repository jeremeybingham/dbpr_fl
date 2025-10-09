"""
City Data Analysis Script

Analyzes city names from DBPR CSV files to understand data quality
and test fuzzy matching strategies before implementation.

Usage:
    python analyze_cities.py [--sample 10000]
"""

import polars as pl
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import Counter
from rapidfuzz import fuzz, process

# Configuration
RAW_DATA_DIR = Path("data/raw")
CITIES_JSON = Path("cities_valid.json")

# CSV columns (from settings.py)
CSV_COLUMNS = [
    'board', 'board_name', 'licensee_name', 'dba_name', 'rank_',
    'address_1', 'address_2', 'address_3', 'city', 'state',
    'zip_', 'county_code', 'county_name', 'license_number',
    'primary_status', 'secondary_status', 'original_license_date',
    'status_effective_date', 'license_expiration_date',
    'alternate_license_number', 'self_proprietors_name',
    'employers_name', 'employers_license_number'
]

# FL county codes (11-77)
FL_COUNTY_CODES = {str(i) for i in range(11, 78)}


def load_valid_cities() -> List[str]:
    """Load the authoritative city list from JSON."""
    with open(CITIES_JSON, 'r') as f:
        cities = json.load(f)
    print(f"✓ Loaded {len(cities)} valid Florida cities from {CITIES_JSON}")
    return cities


def read_csv_files(sample_size: Optional[int] = None) -> pl.DataFrame:
    """
    Read all CSV files and extract relevant columns.
    
    Args:
        sample_size: If provided, randomly sample this many rows
        
    Returns:
        Polars DataFrame with city, state, county_code columns
    """
    csv_files = sorted(RAW_DATA_DIR.glob("RE_rgn*.csv"))
    
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {RAW_DATA_DIR}")
    
    print(f"\n📂 Found {len(csv_files)} CSV files")
    
    dfs = []
    
    for csv_file in csv_files:
        print(f"   Reading {csv_file.name}...", end=" ")
        
        try:
            df = pl.read_csv(
                csv_file,
                has_header=False,
                new_columns=CSV_COLUMNS,
                encoding='utf8-lossy',
                ignore_errors=True,
                truncate_ragged_lines=True,
                dtypes={col: pl.Utf8 for col in CSV_COLUMNS}
            )
            
            # Extract only relevant columns
            df = df.select(['city', 'state', 'county_code'])
            
            # Clean whitespace
            df = df.with_columns([
                pl.col('city').str.strip_chars().replace('', None),
                pl.col('state').str.strip_chars().replace('', None),
                pl.col('county_code').str.strip_chars().replace('', None),
            ])
            
            dfs.append(df)
            print(f"{len(df):,} rows")
            
        except Exception as e:
            print(f"ERROR: {e}")
            continue
    
    if not dfs:
        raise ValueError("No dataframes were successfully loaded")
    
    # Combine all dataframes
    print("\n🔄 Combining dataframes...")
    combined = pl.concat(dfs, how='vertical')
    
    print(f"✓ Total rows: {len(combined):,}")
    
    # Sample if requested
    if sample_size and sample_size < len(combined):
        print(f"🎲 Sampling {sample_size:,} rows...")
        combined = combined.sample(n=sample_size, seed=42)
    
    return combined


def analyze_data_distribution(df: pl.DataFrame) -> Dict:
    """Analyze the distribution of data by state and county."""
    print("\n" + "="*60)
    print("DATA DISTRIBUTION ANALYSIS")
    print("="*60)
    
    stats = {}
    
    # Total records
    stats['total'] = len(df)
    print(f"\n📊 Total records: {stats['total']:,}")
    
    # State distribution (top 10)
    print("\n🗺️  Top 10 States:")
    state_counts = df.group_by('state').agg(pl.count()).sort('count', descending=True).head(10)
    for row in state_counts.iter_rows(named=True):
        state = row['state'] or 'NULL'
        count = row['count']
        pct = (count / stats['total']) * 100
        print(f"   {state:5s} : {count:7,} ({pct:5.1f}%)")
    
    # Florida records
    fl_df = df.filter(pl.col('state') == 'FL')
    stats['florida'] = len(fl_df)
    fl_pct = (stats['florida'] / stats['total']) * 100
    print(f"\n🏖️  Florida records: {stats['florida']:,} ({fl_pct:.1f}%)")
    
    # FL + valid county code
    fl_valid_county = df.filter(
        (pl.col('state') == 'FL') & 
        (pl.col('county_code').is_in(list(FL_COUNTY_CODES)))
    )
    stats['fl_valid_county'] = len(fl_valid_county)
    fl_vc_pct = (stats['fl_valid_county'] / stats['total']) * 100
    print(f"   └─ with valid FL county: {stats['fl_valid_county']:,} ({fl_vc_pct:.1f}%)")
    
    # FL + valid county + non-null city
    fl_normalizable = fl_valid_county.filter(pl.col('city').is_not_null())
    stats['normalizable'] = len(fl_normalizable)
    norm_pct = (stats['normalizable'] / stats['total']) * 100
    print(f"   └─ with non-null city: {stats['normalizable']:,} ({norm_pct:.1f}%)")
    print(f"\n✅ Eligible for normalization: {stats['normalizable']:,} ({norm_pct:.1f}% of total)")
    
    return stats, fl_normalizable


def analyze_city_data(df: pl.DataFrame, valid_cities: List[str]) -> Dict:
    """Analyze city name quality and uniqueness (case-insensitive comparison)."""
    print("\n" + "="*60)
    print("CITY NAME ANALYSIS")
    print("="*60)
    
    stats = {}
    
    # Unique city values
    unique_cities = df['city'].unique().drop_nulls().to_list()
    stats['unique_count'] = len(unique_cities)
    print(f"\n🏙️  Unique city names: {stats['unique_count']:,}")
    
    # Most common cities (top 20)
    print("\n📈 Top 20 Most Common Cities:")
    city_counts = df.group_by('city').agg(pl.count()).sort('count', descending=True).head(20)
    for i, row in enumerate(city_counts.iter_rows(named=True), 1):
        city = row['city']
        count = row['count']
        pct = (count / len(df)) * 100
        print(f"   {i:2d}. {city:30s} : {count:6,} ({pct:4.1f}%)")
    
    # Exact matches with valid cities (case-insensitive)
    valid_cities_lower = set(c.lower() for c in valid_cities)
    exact_matches = [c for c in unique_cities if c.lower() in valid_cities_lower]
    stats['exact_matches'] = len(exact_matches)
    exact_pct = (stats['exact_matches'] / stats['unique_count']) * 100
    print(f"\n✓ Exact matches with valid list (case-insensitive): {stats['exact_matches']:,} / {stats['unique_count']:,} ({exact_pct:.1f}%)")
    
    # Cities not in valid list (sample 20)
    non_matches = [c for c in unique_cities if c.lower() not in valid_cities_lower]
    stats['non_matches'] = len(non_matches)
    print(f"\n❌ Cities NOT in valid list: {stats['non_matches']:,}")
    if non_matches:
        print("\n   Sample of non-matching cities:")
        for city in sorted(non_matches)[:20]:
            print(f"   - {city}")
        if len(non_matches) > 20:
            print(f"   ... and {len(non_matches) - 20:,} more")
    
    return stats


def test_fuzzy_matching(df: pl.DataFrame, valid_cities: List[str], thresholds: List[int] = [70, 75, 80, 85, 90]) -> Dict:
    """Test fuzzy matching at different thresholds (case-insensitive)."""
    print("\n" + "="*60)
    print("FUZZY MATCHING ANALYSIS (case-insensitive)")
    print("="*60)
    
    unique_cities = df['city'].unique().drop_nulls().to_list()
    
    # Create lowercase versions for matching
    valid_cities_lower = [c.lower() for c in valid_cities]
    valid_cities_map = {c.lower(): c for c in valid_cities}  # Map back to original case
    
    results = {}
    
    for threshold in thresholds:
        print(f"\n🎯 Testing threshold: {threshold}%")
        print("-" * 40)
        
        matched = 0
        unmatched = 0
        match_details = []
        
        for city in unique_cities:
            # Use rapidfuzz's process.extractOne for best match (case-insensitive)
            result = process.extractOne(
                city.lower(),
                valid_cities_lower,
                scorer=fuzz.ratio,
                score_cutoff=threshold
            )
            
            if result:
                matched += 1
                match_city_lower, score, _ = result
                match_city = valid_cities_map[match_city_lower]  # Get original case
                
                # Store details for interesting cases
                if score < 100 or city != match_city:  # Not exact match (considering case)
                    match_details.append({
                        'original': city,
                        'matched': match_city,
                        'score': score
                    })
            else:
                unmatched += 1
        
        total = matched + unmatched
        match_rate = (matched / total * 100) if total > 0 else 0
        
        results[threshold] = {
            'matched': matched,
            'unmatched': unmatched,
            'match_rate': match_rate,
            'details': match_details
        }
        
        print(f"   Matched:   {matched:4,} / {total:,} ({match_rate:.1f}%)")
        print(f"   Unmatched: {unmatched:4,} / {total:,}")
        
        # Show some interesting fuzzy matches
        if match_details:
            print(f"\n   Sample fuzzy matches (score < 100):")
            for detail in sorted(match_details, key=lambda x: x['score'])[:10]:
                print(f"   {detail['score']:3.0f}%  '{detail['original']}' → '{detail['matched']}'")
    
    return results


def show_problematic_cities(df: pl.DataFrame, valid_cities: List[str], threshold: int = 80):
    """Show cities that won't match at given threshold (case-insensitive)."""
    print("\n" + "="*60)
    print(f"CITIES THAT WON'T MATCH (< {threshold}% confidence)")
    print("="*60)
    
    unique_cities = df['city'].unique().drop_nulls().to_list()
    
    # Create lowercase versions for matching
    valid_cities_lower = [c.lower() for c in valid_cities]
    valid_cities_map = {c.lower(): c for c in valid_cities}
    
    problematic = []
    
    for city in unique_cities:
        result = process.extractOne(
            city.lower(),
            valid_cities_lower,
            scorer=fuzz.ratio,
            score_cutoff=threshold
        )
        
        if not result:
            # Get best match below threshold
            best = process.extractOne(
                city.lower(),
                valid_cities_lower,
                scorer=fuzz.ratio
            )
            
            if best:
                match_city_lower, score, _ = best
                match_city = valid_cities_map[match_city_lower]
                problematic.append({
                    'city': city,
                    'best_match': match_city,
                    'score': score
                })
    
    if problematic:
        print(f"\n❌ {len(problematic)} cities won't match at {threshold}% threshold:\n")
        
        # Sort by score (lowest first)
        for item in sorted(problematic, key=lambda x: x['score'])[:30]:
            print(f"   {item['score']:3.0f}%  '{item['city']}' → best match: '{item['best_match']}'")
        
        if len(problematic) > 30:
            print(f"\n   ... and {len(problematic) - 30} more")
    else:
        print(f"\n✅ All cities can be matched at {threshold}% threshold!")


def analyze_record_counts(df: pl.DataFrame, valid_cities: List[str], threshold: int = 80):
    """Analyze how many RECORDS (not unique cities) will be affected (case-insensitive)."""
    print("\n" + "="*60)
    print("RECORD-LEVEL IMPACT ANALYSIS")
    print("="*60)
    
    total_records = len(df)
    
    # Create lowercase versions for matching
    valid_cities_lower = [c.lower() for c in valid_cities]
    valid_cities_map = {c.lower(): c for c in valid_cities}
    
    # Create a mapping of city -> normalized city
    unique_cities = df['city'].unique().drop_nulls().to_list()
    city_mapping = {}
    
    for city in unique_cities:
        result = process.extractOne(
            city.lower(),
            valid_cities_lower,
            scorer=fuzz.ratio,
            score_cutoff=threshold
        )
        
        if result:
            match_city_lower, score, _ = result
            match_city = valid_cities_map[match_city_lower]
            city_mapping[city] = match_city
        else:
            city_mapping[city] = None
    
    # Apply mapping to dataframe
    matched_records = sum(1 for city in df['city'].to_list() if city_mapping.get(city) is not None)
    unmatched_records = total_records - matched_records
    
    match_rate = (matched_records / total_records * 100) if total_records > 0 else 0
    
    print(f"\n📊 At {threshold}% threshold:")
    print(f"   Records that will be normalized: {matched_records:,} ({match_rate:.1f}%)")
    print(f"   Records left NULL:              {unmatched_records:,} ({100-match_rate:.1f}%)")
    
    # Show top cities that won't match
    print(f"\n❌ Top 10 cities (by record count) that won't match:")
    
    unmatched_cities = [city for city, norm in city_mapping.items() if norm is None]
    
    city_counts = df.filter(pl.col('city').is_in(unmatched_cities)).group_by('city').agg(
        pl.count().alias('count')
    ).sort('count', descending=True).head(10)
    
    for row in city_counts.iter_rows(named=True):
        city = row['city']
        count = row['count']
        pct = (count / total_records) * 100
        
        # Get best match (case-insensitive)
        best = process.extractOne(city.lower(), valid_cities_lower, scorer=fuzz.ratio)
        best_match = valid_cities_map[best[0]] if best else 'N/A'
        best_score = best[1] if best else 0
        
        print(f"   {city:30s} : {count:5,} records ({pct:4.1f}%) - best: '{best_match}' ({best_score:.0f}%)")


def main(sample_size: Optional[int] = None):
    """Main analysis workflow."""
    print("\n" + "="*60)
    print("DBPR CITY DATA ANALYSIS")
    print("="*60)
    
    # Load valid cities
    valid_cities = load_valid_cities()
    
    # Read CSV files
    df = read_csv_files(sample_size)
    
    # Analyze data distribution
    dist_stats, fl_df = analyze_data_distribution(df)
    
    # Analyze city data quality
    city_stats = analyze_city_data(fl_df, valid_cities)
    
    # Test fuzzy matching at different thresholds
    fuzzy_results = test_fuzzy_matching(fl_df, valid_cities)
    
    # Show problematic cities
    show_problematic_cities(fl_df, valid_cities, threshold=80)
    
    # Analyze record-level impact
    analyze_record_counts(fl_df, valid_cities, threshold=80)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY & RECOMMENDATIONS")
    print("="*60)
    
    print(f"""
📊 Data Overview:
   - Total records analyzed: {dist_stats['total']:,}
   - Eligible for normalization: {dist_stats['normalizable']:,} ({dist_stats['normalizable']/dist_stats['total']*100:.1f}%)
   - Unique city names: {city_stats['unique_count']:,}
   - Exact matches: {city_stats['exact_matches']:,} ({city_stats['exact_matches']/city_stats['unique_count']*100:.1f}%)

🎯 Fuzzy Matching Performance:
""")
    
    for threshold in [70, 75, 80, 85, 90]:
        result = fuzzy_results[threshold]
        print(f"   {threshold}% threshold: {result['match_rate']:.1f}% match rate")
    
    print("\n💡 Recommendations:")
    
    # Find optimal threshold
    threshold_80 = fuzzy_results[80]
    threshold_85 = fuzzy_results[85]
    
    if threshold_80['match_rate'] > 95:
        print("   ✓ 80% threshold achieves >95% match rate - RECOMMENDED")
    elif threshold_85['match_rate'] > 90:
        print("   ✓ Consider 85% threshold for better accuracy")
    else:
        print("   ⚠️  Consider manual review of unmatched cities")
    
    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze DBPR city data")
    parser.add_argument(
        '--sample',
        type=int,
        default=None,
        help='Sample size (default: use all records)'
    )
    
    args = parser.parse_args()
    
    main(sample_size=args.sample)