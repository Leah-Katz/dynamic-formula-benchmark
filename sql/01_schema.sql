/*
    01_schema.sql -- PaymentSystem schema

    Table/column names are dictated by the assignment and must match exactly:
    t_data, t_targil, t_results, t_log.

    Idempotent: drops and recreates every object, so this script alone can
    rebuild the whole schema from a clean (or dirty) PaymentSystem database.
    Run this against the PaymentSystem database (already created with
    recovery model SIMPLE -- see README Step 0).
*/

USE PaymentSystem;
GO

-- Drop in FK-safe order (children before parents) if re-running.
IF OBJECT_ID('dbo.t_results', 'U') IS NOT NULL DROP TABLE dbo.t_results;
IF OBJECT_ID('dbo.t_log', 'U')     IS NOT NULL DROP TABLE dbo.t_log;
IF OBJECT_ID('dbo.t_sample', 'U')  IS NOT NULL DROP TABLE dbo.t_sample;
IF OBJECT_ID('dbo.t_targil', 'U')  IS NOT NULL DROP TABLE dbo.t_targil;
IF OBJECT_ID('dbo.t_data', 'U')    IS NOT NULL DROP TABLE dbo.t_data;
GO

-- t_data: the 1,000,000-row input dataset. data_id is a supplied (not
-- IDENTITY) key so seed_data.py can bulk-load a predictable, reproducible
-- range of ids (1..1000000) rather than relying on server-assigned identity.
CREATE TABLE dbo.t_data (
    data_id INT         NOT NULL PRIMARY KEY,
    a       FLOAT        NOT NULL,
    b       FLOAT        NOT NULL,
    c       FLOAT        NOT NULL,
    d       FLOAT        NOT NULL
);
GO

-- t_targil: the formula catalog. tnai NULL => plain formula (evaluate
-- targil). tnai NOT NULL => conditional (evaluate tnai; if true evaluate
-- targil, else evaluate targil_false). See SEMANTICS.md section 2.
CREATE TABLE dbo.t_targil (
    targil_id    INT          NOT NULL PRIMARY KEY,
    targil       VARCHAR(500) NOT NULL,
    tnai         VARCHAR(500) NULL,
    targil_false VARCHAR(500) NULL
);
GO

-- t_results: the persisted sample (10,000 deterministic data_ids per
-- engine/formula, see SEMANTICS.md / Step 6) plus optional full-dataset
-- persistence via --persist=full. result is NULL for domain errors.
CREATE TABLE dbo.t_results (
    results_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    data_id    INT          NOT NULL FOREIGN KEY REFERENCES dbo.t_data(data_id),
    targil_id  INT          NOT NULL FOREIGN KEY REFERENCES dbo.t_targil(targil_id),
    method     VARCHAR(50)  NOT NULL,
    result     FLOAT        NULL
);
GO

-- Comparison script joins t_results across methods keyed on
-- (targil_id, method, data_id) for every persisted row -- index it.
CREATE INDEX IX_t_results_targil_method_data
    ON dbo.t_results (targil_id, method, data_id);
GO

-- t_sample: the deterministic 10,000-row data_id sample persisted by every
-- engine/formula (Step 6). Generated once (scripts/seed_data.py, seeded
-- RNG) and shared via this table rather than re-derived per engine --
-- reproducing one RNG algorithm bit-for-bit across Python/C#/T-SQL would be
-- fragile and isn't the point of the exercise; a shared table guarantees
-- every method persists the exact same ids trivially.
CREATE TABLE dbo.t_sample (
    data_id INT NOT NULL PRIMARY KEY FOREIGN KEY REFERENCES dbo.t_data(data_id)
);
GO

-- t_log: one row per (targil_id, method) per run, with a split timing
-- breakdown (compile/eval/persist) plus the full-1M-row checksum and NULL
-- count used for cross-engine verification without persisting 1M rows per
-- engine (SEMANTICS.md section 7).
CREATE TABLE dbo.t_log (
    log_id         INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    targil_id      INT          NOT NULL FOREIGN KEY REFERENCES dbo.t_targil(targil_id),
    method         VARCHAR(50)  NOT NULL,
    run_time       FLOAT        NOT NULL,
    rows_processed INT          NOT NULL,
    compile_ms     FLOAT        NOT NULL,
    eval_ms        FLOAT        NOT NULL,
    persist_ms     FLOAT        NOT NULL,
    checksum       FLOAT        NULL,
    null_count     INT          NOT NULL DEFAULT 0,
    run_ts         DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE INDEX IX_t_log_targil_method ON dbo.t_log (targil_id, method);
GO
