import polars as pl
from pathlib import Path
import json

def load_and_process_license_data(data_dir='data/raw'):
    """
    Load CSV files and process Florida real estate license data.
    
    Args:
        data_dir: Directory containing CSV files (default: 'data/raw')
    
    Returns:
        tuple: (processed_df, all_data_df, data_quality_stats)
    """
    
    # Define column names based on the documentation
    column_names = [
        'division',           # 0
        'license_type_code',  # 1
        'name',               # 2
        'dba_name',           # 3
        'license_type_desc',  # 4
        'address1',           # 5
        'address2',           # 6
        'address3',           # 7
        'city',               # 8
        'state',              # 9
        'zip_code',           # 10
        'county_code',        # 11
        'county_name',        # 12
        'license_number',     # 13
        'status1',            # 14
        'status2',            # 15
        'original_license_date',  # 16
        'last_status_change_date', # 17
        'expiration_date',    # 18
        'alternate_license',  # 19
        'proprietor_name',    # 20
        'employer_name',      # 21
        'employer_license_number'  # 22
    ]
    
    # Get CSV files using Path
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Directory not found: {data_path}")
    
    csv_files = sorted(data_path.glob('*.csv'))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in: {data_path}")
    
    print(f"Found {len(csv_files)} CSV files to process")
    
    # Read and combine all CSVs
    dfs = []
    for file in csv_files:
        try:
            df = pl.read_csv(
                file,
                has_header=False,
                new_columns=column_names,
                infer_schema_length=10000,
                ignore_errors=True
            )
            dfs.append(df)
            print(f"Loaded {file.name}: {len(df)} rows")
        except Exception as e:
            print(f"Error loading {file.name}: {e}")
            continue
    
    if not dfs:
        raise ValueError("No data loaded from CSV files")
    
    # Combine all dataframes
    all_data = pl.concat(dfs)
    total_rows = len(all_data)
    print(f"\nTotal rows loaded: {total_rows:,}")
    
    # Initialize data quality tracking
    quality_stats = {
        'total_rows': total_rows,
        'exclusions': {}
    }
    
    # Filter for relevant license types with employers
    target_ranks = ['SL Sales Associate', 'BL Broker Sales', 'BK Broker']
    
    # Track exclusions step by step
    relevant_types = all_data.filter(pl.col('license_type_desc').is_in(target_ranks))
    quality_stats['exclusions']['not_target_license_type'] = total_rows - len(relevant_types)
    
    has_license = relevant_types.filter(pl.col('license_number').is_not_null())
    quality_stats['exclusions']['missing_license_number'] = len(relevant_types) - len(has_license)
    
    has_status = has_license.filter(
        (pl.col('status1').is_not_null()) &
        (pl.col('status2').is_not_null())
    )
    quality_stats['exclusions']['missing_status'] = len(has_license) - len(has_status)
    
    has_employer = has_status.filter(
        (pl.col('employer_license_number').is_not_null()) &
        (pl.col('employer_license_number').str.strip_chars() != '')
    )
    quality_stats['exclusions']['missing_employer'] = len(has_status) - len(has_employer)
    
    filtered_data = has_employer
    
    print(f"\nRows with BK/BL/SL and employer listed: {len(filtered_data):,}")
    
    # Further filter for complete address information
    has_city = filtered_data.filter(
        (pl.col('city').is_not_null()) &
        (pl.col('city').str.strip_chars() != '')
    )
    quality_stats['exclusions']['missing_city'] = len(filtered_data) - len(has_city)
    
    has_state = has_city.filter(
        (pl.col('state').is_not_null()) &
        (pl.col('state').str.strip_chars() != '')
    )
    quality_stats['exclusions']['missing_state'] = len(has_city) - len(has_state)
    
    has_zip = has_state.filter(
        (pl.col('zip_code').is_not_null()) &
        (pl.col('zip_code').cast(pl.Utf8).str.strip_chars() != '')
    )
    quality_stats['exclusions']['missing_zip'] = len(has_state) - len(has_zip)
    
    has_county_code = has_zip.filter(
        (pl.col('county_code').is_not_null()) &
        (pl.col('county_code').cast(pl.Utf8).str.strip_chars() != '')
    )
    quality_stats['exclusions']['missing_county_code'] = len(has_zip) - len(has_county_code)
    
    has_address = has_county_code.filter(
        (pl.col('address1').is_not_null()) &
        (pl.col('address1').str.strip_chars() != '')
    )
    quality_stats['exclusions']['missing_address1'] = len(has_county_code) - len(has_address)
    
    complete_address_data = has_address
    
    quality_stats['final_processed_rows'] = len(complete_address_data)
    quality_stats['total_excluded'] = total_rows - len(complete_address_data)
    quality_stats['inclusion_rate'] = (len(complete_address_data) / total_rows * 100) if total_rows > 0 else 0
    
    print(f"Rows with complete address data: {len(complete_address_data):,}")
    
    return complete_address_data, all_data, quality_stats


def analyze_employer_relationships(employee_data, all_data):
    """
    Analyze employer-employee relationships.
    
    Args:
        employee_data: DataFrame of employees with complete data
        all_data: Complete dataset to match employers
    
    Returns:
        dict: Analysis results
    """
    
    # Get unique employer license numbers from employee data as a list
    employer_licenses_list = employee_data['employer_license_number'].unique().to_list()
    
    # Ensure license_number column is same type as employer_license_number
    # Cast both to string to ensure compatibility
    all_data_typed = all_data.with_columns([
        pl.col('license_number').cast(pl.Utf8)
    ])
    
    employee_data_typed = employee_data.with_columns([
        pl.col('employer_license_number').cast(pl.Utf8)
    ])
    
    # Find matching employers in the full dataset
    employer_matches = all_data_typed.filter(
        pl.col('license_number').is_in(employer_licenses_list)
    )
    
    valid_employer_licenses = set(employer_matches['license_number'].to_list())
    
    # Classify employees as having valid or invalid employer
    employee_data_typed = employee_data_typed.with_columns([
        pl.col('employer_license_number').is_in(list(valid_employer_licenses)).alias('has_valid_employer')
    ])
    
    # Get employer names from all_data
    employer_info = all_data_typed.select([
        'license_number',
        'name',
        'dba_name'
    ]).unique(subset=['license_number'])
    
    # Count employees per employer with city information
    employees_per_employer = employee_data_typed.filter(
        pl.col('has_valid_employer')
    ).group_by('employer_license_number').agg([
        pl.len().alias('employee_count'),
        pl.col('city').value_counts(sort=True).head(5).alias('top_cities_raw')
    ])
    
    # Join with employer info to get employer names
    employees_per_employer = employees_per_employer.join(
        employer_info,
        left_on='employer_license_number',
        right_on='license_number',
        how='left'
    ).select([
        'employer_license_number',
        'name',
        'dba_name',
        'employee_count',
        'top_cities_raw'
    ]).sort('employee_count', descending=True)
    
    # Create detailed employer roster with all employees
    employer_roster = employee_data_typed.filter(
        pl.col('has_valid_employer')
    ).group_by('employer_license_number').agg([
        pl.struct([
            pl.col('name').alias('employee_name'),
            pl.col('license_number').alias('employee_license_number'),
            pl.col('city').alias('employee_city')
        ]).alias('employees')
    ]).join(
        employer_info,
        left_on='employer_license_number',
        right_on='license_number',
        how='left'
    ).with_columns([
        pl.col('employees').list.len().alias('employee_count')
    ]).select([
        'employer_license_number',
        pl.col('name').alias('employer_name'),
        pl.col('dba_name').alias('employer_dba'),
        'employee_count',
        'employees'
    ]).sort('employee_count', descending=True)
    
    # Size category analysis
    size_categories = employees_per_employer.with_columns([
        pl.when(pl.col('employee_count') == 1).then(pl.lit('1 employee'))
        .when(pl.col('employee_count').is_between(2, 5)).then(pl.lit('2-5 employees'))
        .when(pl.col('employee_count').is_between(6, 10)).then(pl.lit('6-10 employees'))
        .when(pl.col('employee_count').is_between(11, 25)).then(pl.lit('11-25 employees'))
        .when(pl.col('employee_count').is_between(26, 50)).then(pl.lit('26-50 employees'))
        .when(pl.col('employee_count').is_between(51, 100)).then(pl.lit('51-100 employees'))
        .otherwise(pl.lit('100+ employees'))
        .alias('size_category')
    ])
    
    size_summary = size_categories.group_by('size_category').agg([
        pl.len().alias('num_employers')
    ]).sort('num_employers', descending=True)
    
    # Calculate statistics
    total_with_employer = len(employee_data_typed)
    valid_employer_count = employee_data_typed.filter(pl.col('has_valid_employer')).height
    invalid_employer_count = total_with_employer - valid_employer_count
    unique_employers = len(employees_per_employer)
    avg_employees = employees_per_employer['employee_count'].mean()
    median_employees = employees_per_employer['employee_count'].median()
    max_employees = employees_per_employer['employee_count'].max()
    
    results = {
        'employee_data': employee_data_typed,
        'employees_per_employer': employees_per_employer,
        'employer_roster': employer_roster,
        'size_summary': size_summary,
        'stats': {
            'total_with_employer': total_with_employer,
            'valid_employer_count': valid_employer_count,
            'invalid_employer_count': invalid_employer_count,
            'unique_employers': unique_employers,
            'avg_employees': avg_employees,
            'median_employees': median_employees,
            'max_employees': max_employees
        }
    }
    
    return results


def load_city_master(file_path='cities_fl.json'):
    """
    Load the city master file for standardizing Florida city names.
    
    Args:
        file_path: Path to the city master JSON file
    
    Returns:
        dict: Nested dictionary for city/variant lookups and county mapping
    """
    with open(file_path, 'r') as f:
        city_data = json.load(f)
    
    # Create lookup dictionaries
    city_to_standard = {}  # Maps city variants to standard city name
    city_county_map = {}   # Maps standard city to county info
    
    for entry in city_data:
        standard_city = entry['city'].upper().strip()
        county_name = entry['county_name']
        county_code = entry['county_code']
        
        # Map the standard city name to itself
        city_to_standard[standard_city] = standard_city
        city_county_map[standard_city] = {
            'county_name': county_name,
            'county_code': county_code
        }
        
        # Map all variants to the standard city name
        for variant in entry.get('variants', []):
            variant_clean = variant.upper().strip()
            city_to_standard[variant_clean] = standard_city
    
    return {
        'city_to_standard': city_to_standard,
        'city_county_map': city_county_map
    }


def normalize_cities(df, city_master):
    """
    Normalize city names in the dataframe using the city master file.
    
    Args:
        df: Polars DataFrame with 'city', 'state', and 'county_code' columns
        city_master: Dictionary from load_city_master()
    
    Returns:
        DataFrame with additional 'normalized_city' and 'city_matched' columns
    """
    city_to_standard = city_master['city_to_standard']
    
    # Add normalized city column
    df_normalized = df.with_columns([
        pl.col('city').str.to_uppercase().str.strip_chars().alias('city_upper')
    ])
    
    # Map cities to standardized names
    df_normalized = df_normalized.with_columns([
        pl.col('city_upper').replace_strict(city_to_standard, default=None, return_dtype=pl.Utf8).alias('normalized_city')
    ])
    
    # Mark which records were successfully matched
    df_normalized = df_normalized.with_columns([
        pl.col('normalized_city').is_not_null().alias('city_matched')
    ])
    
    return df_normalized


def analyze_geographic_distribution(employee_data, city_master, min_employees=10):
    """
    Analyze geographic distribution of employees, focusing on large offices.
    
    Args:
        employee_data: DataFrame with employee data including normalized cities
        city_master: Dictionary from load_city_master()
        min_employees: Minimum number of employees to include employer in detailed analysis
    
    Returns:
        dict: Geographic analysis results
    """
    
    # Filter for Florida employees only with normalized cities
    fl_employees = employee_data.filter(
        (pl.col('state') == 'FL') &
        (pl.col('city_matched') == True) &
        (pl.col('normalized_city').is_not_null())
    )
    
    print(f"\nFlorida employees with matched cities: {len(fl_employees)}")
    
    # Overall city distribution
    city_distribution = fl_employees.group_by('normalized_city').agg([
        pl.len().alias('employee_count')
    ]).sort('employee_count', descending=True)
    
    # Overall county distribution
    county_distribution = fl_employees.group_by('county_name').agg([
        pl.len().alias('employee_count')
    ]).sort('employee_count', descending=True)
    
    # Employer-level geographic analysis
    employer_geography = fl_employees.group_by(['employer_license_number', 'normalized_city', 'county_name']).agg([
        pl.len().alias('employees_in_location')
    ])
    
    # Get total employees per employer
    employer_totals = fl_employees.group_by('employer_license_number').agg([
        pl.len().alias('total_employees')
    ])
    
    # Join to get percentages
    employer_geography = employer_geography.join(
        employer_totals,
        on='employer_license_number',
        how='left'
    ).with_columns([
        (pl.col('employees_in_location') / pl.col('total_employees') * 100).alias('percent_in_location')
    ])
    
    # Filter for large employers
    large_employers = employer_geography.filter(
        pl.col('total_employees') >= min_employees
    ).sort(['total_employees', 'employees_in_location'], descending=True)
    
    # City diversity analysis - how many cities does each large employer operate in?
    # Get top 5 cities by employee count for each employer
    employer_city_data = fl_employees.filter(
        pl.col('has_valid_employer')
    ).group_by(['employer_license_number', 'normalized_city']).agg([
        pl.len().alias('city_employee_count')
    ])
    
    # Rank cities within each employer
    employer_city_ranked = employer_city_data.with_columns([
        pl.col('city_employee_count').rank(method='ordinal', descending=True).over('employer_license_number').alias('city_rank')
    ]).filter(
        pl.col('city_rank') <= 5
    ).sort(['employer_license_number', 'city_rank'])
    
    # Aggregate top 5 cities into a list
    employer_top_cities = employer_city_ranked.group_by('employer_license_number').agg([
        pl.struct(['normalized_city', 'city_employee_count']).alias('top_cities')
    ])
    
    # Get overall employer stats
    employer_city_spread = fl_employees.filter(
        pl.col('has_valid_employer')
    ).group_by('employer_license_number').agg([
        pl.len().alias('total_employees'),
        pl.col('normalized_city').n_unique().alias('num_cities'),
        pl.col('county_name').n_unique().alias('num_counties')
    ]).join(
        employer_top_cities,
        on='employer_license_number',
        how='left'
    ).filter(
        pl.col('total_employees') >= min_employees
    ).sort('total_employees', descending=True)
    
    # County-level employer analysis
    employers_by_county = fl_employees.group_by(['county_name', 'employer_license_number']).agg([
        pl.len().alias('employees_in_county')
    ]).group_by('county_name').agg([
        pl.len().alias('num_employers'),
        pl.col('employees_in_county').sum().alias('total_employees'),
        pl.col('employees_in_county').mean().alias('avg_employees_per_employer')
    ]).sort('total_employees', descending=True)
    
    # City-level employer analysis
    employers_by_city = fl_employees.group_by(['normalized_city', 'employer_license_number']).agg([
        pl.len().alias('employees_in_city')
    ]).group_by('normalized_city').agg([
        pl.len().alias('num_employers'),
        pl.col('employees_in_city').sum().alias('total_employees'),
        pl.col('employees_in_city').mean().alias('avg_employees_per_employer'),
        pl.col('employees_in_city').max().alias('max_employees_single_employer')
    ]).sort('total_employees', descending=True)
    
    results = {
        'fl_employees': fl_employees,
        'city_distribution': city_distribution,
        'county_distribution': county_distribution,
        'large_employer_locations': large_employers,
        'employer_city_spread': employer_city_spread,
        'employers_by_county': employers_by_county,
        'employers_by_city': employers_by_city
    }
    
    return results


def print_reports(results):
    """Print employer-employee relationship reports."""
    
    print("\n" + "="*60)
    print("EMPLOYER SIZE DISTRIBUTION")
    print("="*60)
    print(results['size_summary'])
    
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    stats = results['stats']
    metrics_df = pl.DataFrame({
        'metric': [
            'Total BK/BL/SL Current Active with employer listed',
            'Employees with valid employer license',
            'Employees with invalid employer license',
            'Total unique employers',
            'Average employees per employer',
            'Median employees per employer',
            'Max employees for single employer'
        ],
        'value': [
            float(stats['total_with_employer']),
            float(stats['valid_employer_count']),
            float(stats['invalid_employer_count']),
            float(stats['unique_employers']),
            stats['avg_employees'],
            stats['median_employees'],
            float(stats['max_employees'])
        ]
    })
    print(metrics_df)
    
    print("\n" + "="*60)
    print("TOP 10 EMPLOYERS BY EMPLOYEE COUNT")
    print("="*60)
    print(results['employees_per_employer'].head(10))
    
    print("\n" + "="*60)
    print("ADDRESS COMPLETENESS")
    print("="*60)
    address_stats = {
        'total_records_with_complete_addresses': len(results['employee_data']),
        'unique_cities_in_data': results['employee_data']['city'].n_unique(),
    }
    for key, value in address_stats.items():
        print(f"{key}: {value}")


def print_geographic_reports(geo_results):
    """Print geographic distribution reports."""
    
    print("\n" + "="*80)
    print("TOP 20 CITIES BY EMPLOYEE COUNT")
    print("="*80)
    print(geo_results['city_distribution'].head(20))
    
    print("\n" + "="*80)
    print("TOP 15 COUNTIES BY EMPLOYEE COUNT")
    print("="*80)
    print(geo_results['county_distribution'].head(15))
    
    print("\n" + "="*80)
    print("EMPLOYER GEOGRAPHIC DIVERSITY (Large Employers with 10+ employees)")
    print("="*80)
    print(geo_results['employer_city_spread'].head(20))
    
    print("\n" + "="*80)
    print("CITY-LEVEL EMPLOYER STATISTICS (Top 20)")
    print("="*80)
    print(geo_results['employers_by_city'].head(20))
    
    print("\n" + "="*80)
    print("COUNTY-LEVEL EMPLOYER STATISTICS (Top 15)")
    print("="*80)
    print(geo_results['employers_by_county'].head(15))
    
    print("\n" + "="*80)
    print("LARGE EMPLOYER LOCATION BREAKDOWN (Top 30 entries)")
    print("="*80)
    print(geo_results['large_employer_locations'].head(30))


def print_data_quality_report(quality_stats):
    """Print detailed data quality report."""
    
    print("\n" + "="*80)
    print("DATA QUALITY REPORT")
    print("="*80)
    
    total = quality_stats['total_rows']
    final = quality_stats['final_processed_rows']
    excluded = quality_stats['total_excluded']
    
    print(f"\nTotal rows in source data:     {total:,}")
    print(f"Rows included in analysis:     {final:,} ({quality_stats['inclusion_rate']:.1f}%)")
    print(f"Rows excluded from analysis:   {excluded:,} ({(excluded/total*100):.1f}%)")
    
    print("\n" + "-"*80)
    print("EXCLUSION BREAKDOWN")
    print("-"*80)
    
    exclusions = quality_stats['exclusions']
    
    print(f"\nNot target license type (BK/BL/SL):  {exclusions['not_target_license_type']:,}")
    print(f"  └─ Remaining after filter:          {total - exclusions['not_target_license_type']:,}")
    
    print(f"\nMissing license number:               {exclusions['missing_license_number']:,}")
    print(f"Missing status fields:                {exclusions['missing_status']:,}")
    print(f"Missing employer information:         {exclusions['missing_employer']:,}")
    
    address_exclusions = (
        exclusions['missing_city'] + 
        exclusions['missing_state'] + 
        exclusions['missing_zip'] + 
        exclusions['missing_county_code'] + 
        exclusions['missing_address1']
    )
    
    print(f"\nIncomplete address data:              {address_exclusions:,}")
    print(f"  ├─ Missing city:                    {exclusions['missing_city']:,}")
    print(f"  ├─ Missing state:                   {exclusions['missing_state']:,}")
    print(f"  ├─ Missing ZIP code:                {exclusions['missing_zip']:,}")
    print(f"  ├─ Missing county code:             {exclusions['missing_county_code']:,}")
    print(f"  └─ Missing address line 1:          {exclusions['missing_address1']:,}")
    
    print("\n" + "-"*80)
    print("SUMMARY")
    print("-"*80)
    
    if quality_stats['inclusion_rate'] >= 90:
        quality = "Excellent"
    elif quality_stats['inclusion_rate'] >= 75:
        quality = "Good"
    elif quality_stats['inclusion_rate'] >= 50:
        quality = "Fair"
    else:
        quality = "Poor"
    
    print(f"\nData Quality Rating: {quality}")
    print(f"Coverage: {quality_stats['inclusion_rate']:.1f}% of source records included in analysis")
    
    if quality_stats['inclusion_rate'] < 90:
        print("\nNote: Some records were excluded due to missing required fields.")
        print("This is normal - not all license records have complete employer/address data.")
    
    print()


def main():
    """Print analysis reports."""
    
    print("\n" + "="*60)
    print("EMPLOYER SIZE DISTRIBUTION")
    print("="*60)
    print(results['size_summary'])
    
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    stats = results['stats']
    metrics_df = pl.DataFrame({
        'metric': [
            'Total BK/BL/SL Current Active with employer listed',
            'Employees with valid employer license',
            'Employees with invalid employer license',
            'Total unique employers',
            'Average employees per employer',
            'Median employees per employer',
            'Max employees for single employer'
        ],
        'value': [
            float(stats['total_with_employer']),
            float(stats['valid_employer_count']),
            float(stats['invalid_employer_count']),
            float(stats['unique_employers']),
            stats['avg_employees'],
            stats['median_employees'],
            float(stats['max_employees'])
        ]
    })
    print(metrics_df)
    
    print("\n" + "="*60)
    print("TOP 10 EMPLOYERS BY EMPLOYEE COUNT")
    print("="*60)
    print(results['employees_per_employer'].head(10))
    
    print("\n" + "="*60)
    print("ADDRESS COMPLETENESS")
    print("="*60)
    address_stats = {
        'total_records_with_complete_addresses': len(results['employee_data']),
        'unique_cities_in_data': results['employee_data']['city'].n_unique(),
    }
    for key, value in address_stats.items():
        print(f"{key}: {value}")


def main():
    """Main execution function."""
    
    # Create output directory if it doesn't exist
    output_dir = Path('data/processed')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load and process data
    print("Loading CSV files from data/raw...")
    employee_data, all_data, quality_stats = load_and_process_license_data('data/raw')
    
    # Print data quality report
    print_data_quality_report(quality_stats)
    
    # Analyze relationships
    print("\nAnalyzing employer-employee relationships...")
    results = analyze_employer_relationships(employee_data, all_data)
    
    # Print reports
    print_reports(results)
    
    # Load city master and normalize cities
    print("\n" + "="*80)
    print("LOADING CITY MASTER FILE AND NORMALIZING CITIES")
    print("="*80)
    city_master = load_city_master('cities_fl.json')
    print(f"Loaded {len(city_master['city_to_standard'])} city names/variants")
    print(f"Loaded {len(city_master['city_county_map'])} standard cities")
    
    # Normalize cities in employee data
    results['employee_data'] = normalize_cities(results['employee_data'], city_master)
    
    # Geographic analysis
    print("\nAnalyzing geographic distribution...")
    geo_results = analyze_geographic_distribution(results['employee_data'], city_master, min_employees=10)
    
    # Print geographic reports
    print_geographic_reports(geo_results)
    
    # Save processed data
    print("\n" + "="*80)
    print("SAVING PROCESSED DATA TO JSON")
    print("="*80)
    
    # Save employer-employee data
    results['employee_data'].write_json(output_dir / 'employees_with_complete_data.json')
    results['employees_per_employer'].write_json(output_dir / 'employer_employee_counts.json')
    results['employer_roster'].write_json(output_dir / 'employer_roster_with_all_employees.json')
    results['size_summary'].write_json(output_dir / 'employer_size_distribution.json')
    
    # Save summary statistics as JSON
    with open(output_dir / 'summary_statistics.json', 'w') as f:
        json.dump(results['stats'], f, indent=2)
    
    # Save data quality report as JSON
    with open(output_dir / 'data_quality_report.json', 'w') as f:
        json.dump(quality_stats, f, indent=2)
    
    # Save geographic data
    geo_results['city_distribution'].write_json(output_dir / 'city_distribution.json')
    geo_results['county_distribution'].write_json(output_dir / 'county_distribution.json')
    geo_results['employer_city_spread'].write_json(output_dir / 'employer_geographic_diversity.json')
    geo_results['employers_by_city'].write_json(output_dir / 'city_employer_statistics.json')
    geo_results['employers_by_county'].write_json(output_dir / 'county_employer_statistics.json')
    geo_results['large_employer_locations'].write_json(output_dir / 'large_employer_locations.json')
    
    # Create a comprehensive summary report
    summary_report = {
        'analysis_metadata': {
            'total_records_processed': len(all_data),
            'total_employees_analyzed': len(results['employee_data']),
            'florida_employees_with_matched_cities': len(geo_results['fl_employees']),
            'total_unique_employers': results['stats']['unique_employers'],
            'data_quality': {
                'inclusion_rate': quality_stats['inclusion_rate'],
                'total_excluded': quality_stats['total_excluded']
            }
        },
        'employer_statistics': results['stats'],
        'geographic_summary': {
            'total_cities': len(geo_results['city_distribution']),
            'total_counties': len(geo_results['county_distribution']),
            'top_10_cities': geo_results['city_distribution'].head(10).to_dicts(),
            'top_10_counties': geo_results['county_distribution'].head(10).to_dicts()
        },
        'employer_size_distribution': results['size_summary'].to_dicts(),
        'top_20_employers': results['employees_per_employer'].head(20).to_dicts()
    }
    
    with open(output_dir / 'comprehensive_summary_report.json', 'w') as f:
        json.dump(summary_report, f, indent=2)
    
    print(f"\nAnalysis complete! {len(list(output_dir.glob('*.json')))} JSON files saved to data/processed/")
    print("\nOutput files:")
    for json_file in sorted(output_dir.glob('*.json')):
        print(f"  - {json_file.name}")
    
    return results, geo_results


if __name__ == '__main__':
    results, geo_results = main()