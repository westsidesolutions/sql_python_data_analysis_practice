import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Choose in‑memory for speed, or 'analysis.db' for persistence
conn = sqlite3.connect(':memory:')  # or 'analysis.db'

# Load each CSV and write to SQLite (column names become table columns)
tables = {
    'driver_monthly_metrics': 'archive/driver_monthly_metrics.csv',
    'trips': 'archive/trips.csv',
    'drivers': 'archive/drivers.csv',
    'loads': 'archive/loads.csv',
    'delivery_events': 'archive/delivery_events.csv',
    'customers' : 'archive/customers.csv'
}

for table_name, file_path in tables.items():
    df = pd.read_csv(file_path)
    # Convert date strings to datetime objects for proper SQLite storage
    if table_name == 'driver_monthly_metrics' and 'month' in df.columns:
        df['month'] = pd.to_datetime(df['month'])
    if table_name == 'trips' and 'pickup_datetime' in df.columns:
        df['pickup_datetime'] = pd.to_datetime(df['pickup_datetime'])
    if table_name == 'delivery_events' and 'scheduled_datetime' in df.columns:
        df['scheduled_datetime'] = pd.to_datetime(df['scheduled_datetime'])
    if table_name == 'customers' and 'contract_start_date' in df.columns:
        df['contract_start_date'] = pd.to_datetime(df['contract_start_date'])
    # Write to SQLite (replace any existing table)
    df.to_sql(table_name, conn, index=False, if_exists='replace')
    print(f"Loaded {len(df):,} rows into table '{table_name}'")

print("\nAll tables loaded. Ready for SQL queries.")

#average revenue potential
query = """
SELECT AVG(annual_revenue_potential)
FROM customers
"""
df_result = pd.read_sql_query(query, conn)
print(df_result)


#which customers have Above-Average Annual Revenue Potential (target)
query = """
WITH AvgAnnualRevenuePotential (avg_annual_revenue_potential) AS (
    SELECT AVG(annual_revenue_potential)
    FROM customers
)
SELECT *
FROM customers
WHERE annual_revenue_potential > (
    SELECT avg_annual_revenue_potential
    FROM AvgAnnualRevenuePotential
)
"""
df_result = pd.read_sql_query(query, conn)
print(df_result)


#Query: LAG to compute previous month's miles
query = """
WITH monthly_changes AS (
    SELECT driver_id, month, total_miles, LAG(total_miles) OVER (PARTITION BY driver_id ORDER BY month) AS prev_month_miles, total_miles - LAG(total_miles) OVER (PARTITION BY driver_id ORDER BY month) AS mile_change
    FROM driver_monthly_metrics
    ),
driver_aggregates AS (
    SELECT 
        driver_id, 
        COUNT(month) AS months_count,
        AVG(mile_change) AS avg_change,
        AVG(total_miles) AS avg_miles
    FROM monthly_changes
    WHERE mile_change IS NOT NULL
    GROUP BY driver_id
    HAVING months_count >= 12
        AND avg_change > 0

)
SELECT
    driver_id,
    ROUND(avg_change, 2) AS avg_mile_change,
    ROUND(avg_miles, 2) AS avg_total_miles
FROM driver_aggregates
ORDER BY avg_change DESC
LIMIT 10;

"""
df_result = pd.read_sql_query(query, conn)
print(df_result)

import matplotlib.pyplot as plt
import pandas as pd

# Assuming df_result is already loaded from the SQL query
# df_result columns: driver_id, avg_mile_change, avg_total_miles

plt.figure(figsize=(10, 6))
bars = plt.barh(df_result['driver_id'], df_result['avg_mile_change'], color='steelblue')

# Add value labels at the end of each bar
for bar in bars:
    width = bar.get_width()
    plt.text(width + 5, bar.get_y() + bar.get_height()/2,
             f'{width:.1f}',
             va='center', fontsize=9)

plt.xlabel('Average Monthly Mile Change (miles)')
plt.title('Top 10 Drivers by Mileage Improvement')
plt.gca().invert_yaxis()  # highest at top
plt.tight_layout()

# Optional: save the figure
plt.savefig('top_mileage_improvers.png', dpi=150)

plt.show()

#Who are the top 5 most fuel-efficient drivers in the latest month, and what region do they work in?
query = """
WITH latest_month AS (
    SELECT MAX(month) AS max_month FROM driver_monthly_metrics
),
top_drivers AS (
    SELECT
        dm.driver_id,
        dm.average_mpg,
        dm.total_miles,
        RANK() OVER (ORDER BY dm.average_mpg DESC) AS mpg_rank
    FROM driver_monthly_metrics dm
    WHERE dm.month = (SELECT max_month FROM latest_month)
)
SELECT
    td.driver_id,
    d.first_name || ' ' || d.last_name AS driver_name,
    d.home_terminal,   -- instead of d.region
    td.average_mpg,
    td.total_miles,
    td.mpg_rank
FROM top_drivers td
JOIN drivers d ON td.driver_id = d.driver_id
WHERE td.mpg_rank <= 5
ORDER BY td.mpg_rank;
"""
df_result = pd.read_sql_query(query, conn)
print(df_result)

import matplotlib.pyplot as plt

# df_result has columns: driver_id, driver_name, home_terminal, average_mpg, total_miles, mpg_rank

# Sort by MPG descending (already sorted by rank, but let's be safe)
df_sorted = df_result.sort_values('average_mpg', ascending=True)  # ascending for horizontal bar

plt.figure(figsize=(10, 6))
bars = plt.barh(df_sorted['driver_name'], df_sorted['average_mpg'], color='mediumseagreen')

# Add labels: MPG value and total miles as subtext
for bar, mpg, miles, terminal in zip(bars, df_sorted['average_mpg'], df_sorted['total_miles'], df_sorted['home_terminal']):
    plt.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2,
             f'{mpg:.2f} MPG\n{miles:,.0f} mi', 
             va='center', fontsize=9)

# Add terminal as x-axis label or annotation
# We can add a second line on the y-axis label to show terminal
# But we'll just include it in the bar label

plt.xlabel('Average MPG')
plt.title('Top 5 Most Fuel-Efficient Drivers (Latest Month)')
plt.gca().invert_yaxis()  # highest at top
plt.tight_layout()
plt.savefig('top_efficient_drivers.png', dpi=150)
plt.show()

#Query: Rank drivers by month-to-month efficiency rankings.
query = """
WITH monthly_ranks AS (
    SELECT
        driver_id,
        month,
        average_mpg,
        total_miles,
        RANK() OVER (PARTITION BY month ORDER BY average_mpg DESC) AS mpg_rank,
        DENSE_RANK() OVER (PARTITION BY month ORDER BY average_mpg DESC) AS mpg_dense_rank
    FROM driver_monthly_metrics
)
SELECT
    driver_id,
    average_mpg,
    total_miles,
    mpg_rank,
    mpg_dense_rank
FROM monthly_ranks
WHERE month = (SELECT MAX(month) FROM driver_monthly_metrics)  -- Filter to latest month
ORDER BY mpg_rank
LIMIT 10;  -- Show only top 10
"""
df_result = pd.read_sql_query(query,conn)
print(df_result)

query = """
WITH rolling AS (
    SELECT
        driver_id,
        month,
        total_miles,
        AVG(total_miles) OVER (
            PARTITION BY driver_id
            ORDER BY month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS rolling_3mo_avg
    FROM driver_monthly_metrics
)
SELECT
    driver_id,
    month,
    total_miles,
    ROUND(rolling_3mo_avg, 2) AS rolling_avg,
    ROUND((total_miles - rolling_3mo_avg) / rolling_3mo_avg * 100, 2) AS pct_deviation
FROM rolling
WHERE month = (SELECT MAX(month) FROM driver_monthly_metrics)
  AND total_miles < rolling_3mo_avg * 0.8
ORDER BY pct_deviation ASC;
"""
df_result = pd.read_sql_query(query,conn)
print(df_result)

import matplotlib.pyplot as plt

# df_result columns: driver_id, month, total_miles, rolling_avg, pct_deviation
# Already sorted by pct_deviation ascending (most negative first)

plt.figure(figsize=(10, 8))

# Create horizontal bar chart
bars = plt.barh(df_result['driver_id'], df_result['pct_deviation'], color='tomato')

# Add value labels and extra info
for bar, driver, miles, avg, pct in zip(bars,
                                        df_result['driver_id'],
                                        df_result['total_miles'],
                                        df_result['rolling_avg'],
                                        df_result['pct_deviation']):
    # Position text at the end of the bar (slightly to the right)
    plt.text(pct + 0.5, bar.get_y() + bar.get_height()/2,
             f'{pct:.1f}% drop\nMiles: {miles:,.0f} (Avg: {avg:,.0f})',
             va='center', fontsize=8)

# Add vertical line at 0 for reference
plt.axvline(x=0, color='black', linestyle='-', alpha=0.3)

plt.xlabel('Percent Deviation from 3-Month Rolling Average')
plt.title('Drivers with >20% Drop in Miles (Latest Month)')
plt.gca().invert_yaxis()  # highest severity at top
plt.tight_layout()
plt.savefig('rolling_drop_drivers.png', dpi=150)
plt.show()

#Percentile Bucketing with NTILE()
#revenue potential by quartile
query = """
SELECT
    customer_id,
    annual_revenue_potential,
    NTILE(4) OVER (ORDER BY annual_revenue_potential DESC) as revenue_potential_quartile
FROM customers
WHERE contract_start_date LIKE '2021%'
"""
df_result = pd.read_sql_query(query,conn)
print(df_result)

import matplotlib.pyplot as plt

# df_result columns: customer_id, annual_revenue_potential, revenue_potential_quartile

# Aggregate: count and average revenue per quartile
quartile_summary = df_result.groupby('revenue_potential_quartile').agg(
    count=('customer_id', 'size'),
    avg_revenue=('annual_revenue_potential', 'mean')
).reset_index()

# Sort by quartile (1 = highest revenue)
quartile_summary = quartile_summary.sort_values('revenue_potential_quartile')

plt.figure(figsize=(10, 6))

# Bar chart of average revenue by quartile
bars = plt.bar(quartile_summary['revenue_potential_quartile'].astype(str),
               quartile_summary['avg_revenue'],
               color=['darkblue', 'royalblue', 'steelblue', 'lightblue'])

# Add labels: average revenue and count
for bar, row in zip(bars, quartile_summary.itertuples()):
    plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 100000,
             f'${row.avg_revenue:,.0f}\n{row.count} customers',
             ha='center', va='bottom', fontsize=9)

plt.xlabel('Revenue Quartile (1 = Highest Potential)')
plt.ylabel('Average Annual Revenue Potential')
plt.title('Customer Revenue Segmentation by Quartile (2021 Contracts)')
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig('customer_quartiles.png', dpi=150)
plt.show()