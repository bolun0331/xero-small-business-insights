/*
    Convenience views for ad hoc SQL analysis. Power BI should import the star
    schema tables directly; these views are for querying in SSMS.
*/

-- One readable row per value
CREATE OR ALTER VIEW xsbi.vMetric AS
SELECT
    c.CountryCode,
    c.CountryName,
    s.SegmentType,
    s.SegmentName,
    m.MetricName,
    m.Unit,
    d.[Date]        AS MonthStart,
    d.YearMonth,
    f.Value
FROM xsbi.FactMetric f
JOIN xsbi.DimCountry c ON c.CountryKey = f.CountryKey
JOIN xsbi.DimSegment s ON s.SegmentKey = f.SegmentKey
JOIN xsbi.DimMetric  m ON m.MetricKey  = f.MetricKey
JOIN xsbi.DimDate    d ON d.DateKey    = f.DateKey;
GO

-- Latest 3-month average vs the 2019 (pre-COVID) average, per segment and metric.
-- Monthly regional and industry figures are noisy, so compare averages, not single months.
CREATE OR ALTER VIEW xsbi.vLatestVs2019 AS
WITH latest AS (
    SELECT MAX(DateKey) AS MaxDateKey FROM xsbi.FactMetric
),
last3 AS (
    SELECT TOP (3) DateKey FROM xsbi.DimDate
    WHERE DateKey <= (SELECT MaxDateKey FROM latest)
    ORDER BY DateKey DESC
),
-- Flag each row first: SQL Server doesn't allow a subquery inside AVG()
flagged AS (
    SELECT
        f.CountryKey,
        f.SegmentKey,
        f.MetricKey,
        f.Value,
        CASE WHEN l.DateKey IS NOT NULL THEN 1 ELSE 0 END                   AS IsLast3,
        CASE WHEN f.DateKey BETWEEN 20190101 AND 20191201 THEN 1 ELSE 0 END AS Is2019
    FROM xsbi.FactMetric f
    LEFT JOIN last3 l ON l.DateKey = f.DateKey
)
SELECT
    c.CountryCode,
    s.SegmentType,
    s.SegmentName,
    m.MetricName,
    m.Unit,
    m.HigherIsBetter,
    CAST(AVG(CASE WHEN f.IsLast3 = 1 THEN f.Value END) AS DECIMAL(9,2)) AS Last3MonthAvg,
    CAST(AVG(CASE WHEN f.Is2019 = 1 THEN f.Value END) AS DECIMAL(9,2))  AS Avg2019,
    CAST(AVG(CASE WHEN f.IsLast3 = 1 THEN f.Value END)
       - AVG(CASE WHEN f.Is2019 = 1 THEN f.Value END) AS DECIMAL(9,2))  AS ChangeVs2019
FROM flagged f
JOIN xsbi.DimCountry c ON c.CountryKey = f.CountryKey
JOIN xsbi.DimSegment s ON s.SegmentKey = f.SegmentKey
JOIN xsbi.DimMetric  m ON m.MetricKey  = f.MetricKey
GROUP BY c.CountryCode, s.SegmentType, s.SegmentName, s.SortOrder, m.MetricName, m.Unit, m.HigherIsBetter, m.SortOrder;
GO

