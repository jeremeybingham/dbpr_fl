# Florida DBPR Real Estate License File Analysis

A comprehensive data analysis system for Florida real estate licenses, providing insights into employer-employee relationships and geographic distribution.

## Overview

This project analyzes Florida real estate license data to:
- Map employer-employee relationships
- Analyze geographic distribution of real estate professionals
- Identify large employers and their workforce distribution
- Provide interactive search capabilities for employee rosters

The Florida DBPR license files are provided as 14 large regional CSV files. They contain significant data quality issues, but with proper processing can yield insights.

## Prerequisites

- Python 3.8+
- Required Python packages:
  - `polars` - High-performance DataFrame library


## Installation

1. **Clone or download this project**

2. **Install dependencies:**
```bash
pip install polars
```

Or use a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install polars
```

## Project Structure

```
project/
├── stats.py                   # Main analysis script
├── download.py                # FTP download script for CSV files
├── serve.py                   # HTTP server for dashboard
├── dashboard.html             # Interactive web dashboard
├── cities_fl.json             # City name standardization data
├── data/
│   ├── raw/                   # Place CSV files here
│   │   ├── RE_rgn1.csv
│   │   ├── ...
│   │   └── RE_rgn14.csv
│   └── processed/             # Generated JSON reports (created automatically)
└── README.md
```

## Setup

### 1. Prepare Your Data

Use the included download script to fetch files directly from the Florida DBPR FTP server:

```bash
python download.py
```

This will download all 14 regional CSV files (RE_rgn1.csv through RE_rgn14.csv) to `data/raw/`. The download typically takes 2-5 minutes depending on your connection speed (~185 MB total).

### 2. Prepare City Master File

Ensure `cities_fl.json` is in your project root directory. This file contains standardized city names and variants for accurate geographic matching.

## Running the Analysis

Execute the main analysis script:

```bash
python stats.py
```

### What the Script Does

The analysis runs through several stages:

#### Stage 1: Data Loading
- Reads all CSV files from `data/raw/`
- Combines data from multiple files
- Filters for relevant license types (Sales Associates, Broker Sales, Brokers)

#### Stage 2: Employer-Employee Analysis
- Validates employer license numbers
- Counts employees per employer
- Categorizes employers by size (1 employee, 2-5, 6-10, 11-25, 26-50, 51-100, 100+)
- Calculates summary statistics

#### Stage 3: Geographic Analysis
- Normalizes city names using the city master file
- Analyzes distribution by city and county
- Identifies large employers operating across multiple locations
- Calculates employer statistics by geographic area

#### Stage 4: Report Generation
- Creates 13 JSON files in `data/processed/`
- Prints summary reports to console

### Generated Reports

The script creates the following JSON files in `data/processed/`:

| File | Description |
|------|-------------|
| `city_distribution.json` | Employee counts by city (all cities in Florida) |
| `city_employer_statistics.json` | Detailed employer statistics by city (number of employers, avg employees per employer, max single employer) |
| `comprehensive_summary_report.json` | Consolidated summary with top-level metrics, top cities/counties, and top employers |
| `county_distribution.json` | Employee counts by county (all counties in Florida) |
| `county_employer_statistics.json` | Detailed employer statistics by county (number of employers, avg employees per employer) |
| `data_quality_report.json` | Data quality metrics showing inclusion/exclusion rates and reasons for exclusions |
| `employees_with_complete_data.json` | All employee records with complete address data and normalized cities |
| `employer_employee_counts.json` | Summary of each employer with employee count, name, and top 5 cities |
| `employer_geographic_diversity.json` | Large employers (10+) with operations across multiple cities, including top 5 cities by employee count |
| `employer_roster_with_all_employees.json` | Complete roster with array of all employees for each employer (name, license #, city) |
| `employer_size_distribution.json` | Breakdown of employers by size category (1, 2-5, 6-10, 11-25, 26-50, 51-100, 100+ employees) |
| `large_employer_locations.json` | Geographic breakdown showing employee distribution by city/county for large employers |
| `summary_statistics.json` | Overall statistics (totals, averages, medians, valid/invalid employer counts) |

## Viewing the Dashboard

After generating the reports, launch the interactive web dashboard:

### Using the Server Script

```bash
python serve.py
```

Then open your browser to: **http://localhost:8000/dashboard.html**


Press `Ctrl+C` to stop the server when finished.

## Dashboard Features

The interactive dashboard provides several views:

### 1. Summary Statistics
- Total employees analyzed
- Unique employers
- Average and median employees per employer

### 2. Employer Size Distribution
- Breakdown of employers by employee count categories
- Percentage distribution

### 3. Top Employers
- 20 largest employers by employee count
- Shows employer name, license number, and top cities

### 4. Geographic Distribution
- Top 15 cities by employee count
- Top 15 counties by employee count
- Number of employers in each location

### 5. Employer Geographic Diversity
- Large employers (10+ employees) operating across multiple cities
- Shows number of cities and counties
- Lists top 5 cities with employee counts

### 6. City & County Statistics
- Employer density in each location
- Average employees per employer
- Maximum employees for single employer

### 7. Employee Search Interface

The dashboard includes a powerful search tool:

**How to Use:**
1. Type employer name or license number in the search box
2. Select from autocomplete suggestions
3. Optionally filter by city or county
4. Click "Search" to view results
5. Results show all matching employees with their details

**Features:**
- Live autocomplete for all search fields
- Shows filtered employee lists
- Displays employee name, license number, city, and county
- Loading indicator for large searches
- Clear button to reset search

## Troubleshooting

### No CSV Files Found
**Problem:** Script can't find CSV files

**Solution:** Ensure CSV files are in `data/raw/` directory relative to the script

### City Master File Not Found
**Problem:** Script can't find `cities_fl.json`

**Solution:** Ensure `cities_fl.json` is in the project root directory (same level as `stats.py`)

### JSON Files Don't Load in Dashboard
**Problem:** Dashboard shows error or no data

**Solution:**
- Verify all JSON files exist in `data/processed/`
- Check browser console for specific errors
- Ensure HTTP server is running
- Try clearing browser cache

## Performance Notes

- Analysis of ~300,000+ employee records typically completes in 1-2 minutes
- Dashboard loads all data in browser memory for fast searching
- Large employer rosters (1000+ employees) may take several seconds to filter
- Initial page load may take 5-10 seconds depending on data size
