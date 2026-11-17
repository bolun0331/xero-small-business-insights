/*
    XSBI star schema (SQL Server 2016 SP1 or later).
    Safe to run repeatedly: objects are only created if they don't exist.
    run_pipeline.py runs this automatically before each load.
*/

IF SCHEMA_ID(N'xsbi') IS NULL
    EXEC(N'CREATE SCHEMA xsbi');
GO

IF OBJECT_ID(N'xsbi.DimCountry', N'U') IS NULL
CREATE TABLE xsbi.DimCountry (
    CountryKey    INT           NOT NULL CONSTRAINT PK_DimCountry PRIMARY KEY,
    CountryCode   CHAR(2)       NOT NULL CONSTRAINT UQ_DimCountry_Code UNIQUE,
    CountryName   NVARCHAR(50)  NOT NULL
);
GO

IF OBJECT_ID(N'xsbi.DimMetric', N'U') IS NULL
CREATE TABLE xsbi.DimMetric (
    MetricKey       INT           NOT NULL CONSTRAINT PK_DimMetric PRIMARY KEY,
    MetricCode      VARCHAR(30)   NOT NULL CONSTRAINT UQ_DimMetric_Code UNIQUE,
    MetricName      NVARCHAR(50)  NOT NULL,
    Unit            NVARCHAR(20)  NOT NULL,   -- '% y/y', 'days', '% of firms'
    HigherIsBetter  BIT           NOT NULL,   -- drives good/bad colouring in the report
    SortOrder       INT           NOT NULL
);
GO

IF OBJECT_ID(N'xsbi.DimDate', N'U') IS NULL
CREATE TABLE xsbi.DimDate (
    DateKey        INT          NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,  -- yyyymmdd, first of month
    [Date]         DATE         NOT NULL,
    [Year]         SMALLINT     NOT NULL,
    [Quarter]      TINYINT      NOT NULL,
    QuarterLabel   VARCHAR(8)   NOT NULL,   -- 'Q3 2026'
    MonthNumber    TINYINT      NOT NULL,
    MonthName      CHAR(3)      NOT NULL,   -- 'Sep'
    YearMonth      VARCHAR(8)   NOT NULL,   -- 'Sep 2026'
    YearMonthSort  INT          NOT NULL    -- 202609, sort-by column for YearMonth
);
GO

IF OBJECT_ID(N'xsbi.DimSegment', N'U') IS NULL
CREATE TABLE xsbi.DimSegment (
    SegmentKey    INT            NOT NULL CONSTRAINT PK_DimSegment PRIMARY KEY,
    CountryKey    INT            NOT NULL CONSTRAINT FK_DimSegment_Country REFERENCES xsbi.DimCountry (CountryKey),
    CountryCode   CHAR(2)        NOT NULL,
    SegmentType   VARCHAR(10)    NOT NULL,  -- 'National', 'Industry', 'Region' (incl. US states, CA provinces)
    SegmentName   NVARCHAR(100)  NOT NULL,
    SortOrder     INT            NOT NULL,
    CONSTRAINT UQ_DimSegment UNIQUE (CountryKey, SegmentType, SegmentName)
);
GO

IF OBJECT_ID(N'xsbi.FactMetric', N'U') IS NULL
CREATE TABLE xsbi.FactMetric (
    DateKey     INT           NOT NULL CONSTRAINT FK_Fact_Date    REFERENCES xsbi.DimDate (DateKey),
    CountryKey  INT           NOT NULL CONSTRAINT FK_Fact_Country REFERENCES xsbi.DimCountry (CountryKey),
    SegmentKey  INT           NOT NULL CONSTRAINT FK_Fact_Segment REFERENCES xsbi.DimSegment (SegmentKey),
    MetricKey   INT           NOT NULL CONSTRAINT FK_Fact_Metric  REFERENCES xsbi.DimMetric (MetricKey),
    Value       DECIMAL(9,2)  NOT NULL,
    CONSTRAINT PK_FactMetric PRIMARY KEY (SegmentKey, MetricKey, DateKey)
);
GO

IF OBJECT_ID(N'xsbi.LoadLog', N'U') IS NULL
CREATE TABLE xsbi.LoadLog (
    LoadId    INT IDENTITY(1,1)  NOT NULL CONSTRAINT PK_LoadLog PRIMARY KEY,
    LoadedAt  DATETIME2(0)       NOT NULL,
    Release   CHAR(7)            NOT NULL,  -- 'YYYY-MM' of the latest month loaded
    FactRows  INT                NOT NULL
);
GO

