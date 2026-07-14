/*
    02_sp_calc_formula.sql -- T-SQL stored procedure engine.

    This is the method the assignment describes most explicitly ("builds
    the calculation SQL at runtime, executes it with sp_executesql"), so it
    gets the strongest implementation: a genuine recursive-descent parser
    for the SEMANTICS.md grammar, written directly in T-SQL (dbo.sp_pf_*
    procedures below), not a character whitelist or regex approximation.
    Formula strings come from t_targil -- outside this program's trust
    boundary just like every other engine's input -- and the parser IS the
    validation: any character, identifier, or function name outside the
    grammar simply fails to match at some parse position and the whole
    formula is rejected (THROW) before sp_executesql ever sees it. The
    translated output only ever contains column references (a/b/c/d),
    numeric literals, and known SQL functions/operators -- there is no path
    for a raw formula substring to reach the dynamic SQL string unescaped.

    Grammar (mirrors SEMANTICS.md section 2 exactly):
        expr  := term (('+'|'-') term)*
        term  := unary (('*'|'/') unary)*
        unary := '-' unary | power
        power := atom ('^' unary)?
        atom  := NUMBER | IDENT | FUNC1'('expr')' | FUNC2'('expr','expr')' | '('expr')'
        condition (tnai only) := expr ('>'|'<'|'>='|'<='|'=='|'!=') expr

    Each grammar rule below is one small recursive stored procedure that
    both validates its slice of the input AND emits the equivalent T-SQL
    fragment in the same pass -- exactly like formula_parser.py's AST walk
    doubles as validate-then-emit, just implemented as recursive descent
    over character positions instead of over an AST.

    Domain-error guards (SEMANTICS.md section 4) are inserted at the point
    of translation, not bolted on afterward: SQRT/LOG/division/POWER are
    each wrapped in an explicit CASE WHEN / NULLIF guard as they're emitted,
    per the verified runtime behavior of this SQL Server instance (LOG of a
    non-positive number and POWER of a negative base with a fractional
    exponent both raise a hard, batch-aborting error here -- they do NOT
    silently return NULL/NaN the way Python/NumPy/C# do -- so the guards are
    not optional defensive coding, they are the only way to get NULL out of
    a domain error at all).

    Known, disclosed limitation: POWER() can also raise a hard arithmetic-
    overflow error for very large magnitudes, and unlike the negative-base
    case this can't be pre-checked from the operands with a simple CASE
    WHEN. Every formula in the catalog uses small bases/exponents so this
    never triggers in practice; a production system accepting arbitrary
    exponents would need a magnitude pre-check or per-row TRY/CATCH (which
    would give up the set-based performance advantage). See REPORT.md.
*/

USE PaymentSystem;
GO

-- ===========================================================================
-- atom := NUMBER | IDENT | FUNC1'('expr')' | FUNC2'('expr','expr')' | '('expr')'
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_pf_atom
    @formula VARCHAR(500),
    @pos     INT,
    @end_pos INT OUTPUT,
    @sql     VARCHAR(2000) OUTPUT,
    @ok      BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @len INT = LEN(@formula);
    DECLARE @p INT = @pos;
    DECLARE @c CHAR(1);

    SET @ok = 0;
    SET @sql = NULL;

    WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
    IF @p > @len BEGIN SET @end_pos = @p; RETURN; END

    SET @c = SUBSTRING(@formula, @p, 1);

    -- NUMBER: digits with at most one '.'
    IF @c LIKE '[0-9]' OR @c = '.'
    BEGIN
        DECLARE @start INT = @p, @dot_seen BIT = 0;
        WHILE @p <= @len AND (SUBSTRING(@formula, @p, 1) LIKE '[0-9]'
                               OR (SUBSTRING(@formula, @p, 1) = '.' AND @dot_seen = 0))
        BEGIN
            IF SUBSTRING(@formula, @p, 1) = '.' SET @dot_seen = 1;
            SET @p += 1;
        END
        DECLARE @numtext VARCHAR(100) = SUBSTRING(@formula, @start, @p - @start);
        IF @numtext = '.' BEGIN SET @end_pos = @start; RETURN; END
        SET @sql = @numtext;
        SET @ok = 1;
        SET @end_pos = @p;
        RETURN;
    END

    -- IDENT (a/b/c/d) or FUNC1/FUNC2 name
    IF @c LIKE '[a-z]'
    BEGIN
        DECLARE @wstart INT = @p;
        WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) LIKE '[a-z]' SET @p += 1;
        DECLARE @word VARCHAR(20) = SUBSTRING(@formula, @wstart, @p - @wstart);

        IF @word IN ('a', 'b', 'c', 'd')
        BEGIN
            SET @sql = @word;
            SET @ok = 1;
            SET @end_pos = @p;
            RETURN;
        END

        IF @word IN ('sqrt', 'log', 'abs', 'min', 'max', 'pow')
        BEGIN
            WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
            IF @p > @len OR SUBSTRING(@formula, @p, 1) <> '(' BEGIN SET @end_pos = @p; RETURN; END
            SET @p += 1;

            DECLARE @arg1_sql VARCHAR(2000), @arg1_end INT, @arg1_ok BIT;
            EXEC dbo.sp_pf_expr @formula = @formula, @pos = @p, @end_pos = @arg1_end OUTPUT, @sql = @arg1_sql OUTPUT, @ok = @arg1_ok OUTPUT;
            IF @arg1_ok = 0 BEGIN SET @end_pos = @arg1_end; RETURN; END
            SET @p = @arg1_end;

            IF @word IN ('min', 'max', 'pow')
            BEGIN
                WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
                IF @p > @len OR SUBSTRING(@formula, @p, 1) <> ',' BEGIN SET @end_pos = @p; RETURN; END
                SET @p += 1;

                DECLARE @arg2_sql VARCHAR(2000), @arg2_end INT, @arg2_ok BIT;
                EXEC dbo.sp_pf_expr @formula = @formula, @pos = @p, @end_pos = @arg2_end OUTPUT, @sql = @arg2_sql OUTPUT, @ok = @arg2_ok OUTPUT;
                IF @arg2_ok = 0 BEGIN SET @end_pos = @arg2_end; RETURN; END
                SET @p = @arg2_end;

                WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
                IF @p > @len OR SUBSTRING(@formula, @p, 1) <> ')' BEGIN SET @end_pos = @p; RETURN; END
                SET @p += 1;

                IF @word = 'min' SET @sql = 'LEAST(' + @arg1_sql + ',' + @arg2_sql + ')';
                ELSE IF @word = 'max' SET @sql = 'GREATEST(' + @arg1_sql + ',' + @arg2_sql + ')';
                ELSE SET @sql = '(CASE WHEN (' + @arg1_sql + ') >= 0 OR (' + @arg2_sql + ') = ROUND((' + @arg2_sql + '), 0) THEN POWER((' + @arg1_sql + '), (' + @arg2_sql + ')) ELSE NULL END)';

                SET @ok = 1;
                SET @end_pos = @p;
                RETURN;
            END
            ELSE
            BEGIN
                WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
                IF @p > @len OR SUBSTRING(@formula, @p, 1) <> ')' BEGIN SET @end_pos = @p; RETURN; END
                SET @p += 1;

                IF @word = 'sqrt' SET @sql = '(CASE WHEN (' + @arg1_sql + ') >= 0 THEN SQRT((' + @arg1_sql + ')) ELSE NULL END)';
                ELSE IF @word = 'log' SET @sql = '(CASE WHEN (' + @arg1_sql + ') > 0 THEN LOG((' + @arg1_sql + ')) ELSE NULL END)';
                ELSE SET @sql = 'ABS((' + @arg1_sql + '))';

                SET @ok = 1;
                SET @end_pos = @p;
                RETURN;
            END
        END

        -- unknown identifier/function -- reject (this IS the security boundary)
        SET @end_pos = @wstart;
        RETURN;
    END

    IF @c = '('
    BEGIN
        SET @p += 1;
        DECLARE @inner_sql VARCHAR(2000), @inner_end INT, @inner_ok BIT;
        EXEC dbo.sp_pf_expr @formula = @formula, @pos = @p, @end_pos = @inner_end OUTPUT, @sql = @inner_sql OUTPUT, @ok = @inner_ok OUTPUT;
        IF @inner_ok = 0 BEGIN SET @end_pos = @inner_end; RETURN; END
        SET @p = @inner_end;
        WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
        IF @p > @len OR SUBSTRING(@formula, @p, 1) <> ')' BEGIN SET @end_pos = @p; RETURN; END
        SET @p += 1;
        SET @sql = '(' + @inner_sql + ')';
        SET @ok = 1;
        SET @end_pos = @p;
        RETURN;
    END

    -- unexpected character -- reject
    SET @end_pos = @p;
END
GO

-- ===========================================================================
-- power := atom ('^' unary)?    -- '^' guarded: negative base needs an
-- integer exponent (SEMANTICS.md section 4 / verified SQL Server behavior).
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_pf_power
    @formula VARCHAR(500),
    @pos     INT,
    @end_pos INT OUTPUT,
    @sql     VARCHAR(2000) OUTPUT,
    @ok      BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @len INT = LEN(@formula);
    DECLARE @base_sql VARCHAR(2000), @p INT;

    EXEC dbo.sp_pf_atom @formula = @formula, @pos = @pos, @end_pos = @p OUTPUT, @sql = @base_sql OUTPUT, @ok = @ok OUTPUT;
    IF @ok = 0 BEGIN SET @end_pos = @p; RETURN; END

    DECLARE @scan INT = @p;
    WHILE @scan <= @len AND SUBSTRING(@formula, @scan, 1) = ' ' SET @scan += 1;

    IF @scan <= @len AND SUBSTRING(@formula, @scan, 1) = '^'
    BEGIN
        SET @scan += 1;
        DECLARE @exp_sql VARCHAR(2000), @exp_end INT, @exp_ok BIT;
        EXEC dbo.sp_pf_unary @formula = @formula, @pos = @scan, @end_pos = @exp_end OUTPUT, @sql = @exp_sql OUTPUT, @ok = @exp_ok OUTPUT;
        IF @exp_ok = 0 BEGIN SET @ok = 0; SET @end_pos = @exp_end; RETURN; END
        SET @sql = '(CASE WHEN (' + @base_sql + ') >= 0 OR (' + @exp_sql + ') = ROUND((' + @exp_sql + '), 0) THEN POWER((' + @base_sql + '), (' + @exp_sql + ')) ELSE NULL END)';
        SET @end_pos = @exp_end;
        SET @ok = 1;
        RETURN;
    END

    SET @sql = @base_sql;
    SET @end_pos = @p;
    SET @ok = 1;
END
GO

-- ===========================================================================
-- unary := '-' unary | power
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_pf_unary
    @formula VARCHAR(500),
    @pos     INT,
    @end_pos INT OUTPUT,
    @sql     VARCHAR(2000) OUTPUT,
    @ok      BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @len INT = LEN(@formula);
    DECLARE @p INT = @pos;
    WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;

    IF @p <= @len AND SUBSTRING(@formula, @p, 1) = '-'
    BEGIN
        SET @p += 1;
        DECLARE @inner_sql VARCHAR(2000), @inner_end INT, @inner_ok BIT;
        EXEC dbo.sp_pf_unary @formula = @formula, @pos = @p, @end_pos = @inner_end OUTPUT, @sql = @inner_sql OUTPUT, @ok = @inner_ok OUTPUT;
        IF @inner_ok = 0 BEGIN SET @ok = 0; SET @end_pos = @inner_end; RETURN; END
        SET @sql = '(-(' + @inner_sql + '))';
        SET @end_pos = @inner_end;
        SET @ok = 1;
        RETURN;
    END

    EXEC dbo.sp_pf_power @formula = @formula, @pos = @p, @end_pos = @end_pos OUTPUT, @sql = @sql OUTPUT, @ok = @ok OUTPUT;
END
GO

-- ===========================================================================
-- term := unary (('*'|'/') unary)*    -- '/' guarded via NULLIF (denominator, 0)
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_pf_term
    @formula VARCHAR(500),
    @pos     INT,
    @end_pos INT OUTPUT,
    @sql     VARCHAR(2000) OUTPUT,
    @ok      BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @len INT = LEN(@formula);
    DECLARE @left_sql VARCHAR(2000), @p INT;

    EXEC dbo.sp_pf_unary @formula = @formula, @pos = @pos, @end_pos = @p OUTPUT, @sql = @left_sql OUTPUT, @ok = @ok OUTPUT;
    IF @ok = 0 BEGIN SET @end_pos = @p; RETURN; END

    WHILE 1 = 1
    BEGIN
        DECLARE @scan INT = @p;
        WHILE @scan <= @len AND SUBSTRING(@formula, @scan, 1) = ' ' SET @scan += 1;
        IF @scan > @len BREAK;
        DECLARE @op CHAR(1) = SUBSTRING(@formula, @scan, 1);
        IF @op <> '*' AND @op <> '/' BREAK;
        SET @scan += 1;

        DECLARE @right_sql VARCHAR(2000), @right_end INT, @right_ok BIT;
        EXEC dbo.sp_pf_unary @formula = @formula, @pos = @scan, @end_pos = @right_end OUTPUT, @sql = @right_sql OUTPUT, @ok = @right_ok OUTPUT;
        IF @right_ok = 0 BEGIN SET @ok = 0; SET @end_pos = @right_end; RETURN; END

        IF @op = '*'
            SET @left_sql = '(' + @left_sql + ' * ' + @right_sql + ')';
        ELSE
            SET @left_sql = '(' + @left_sql + ' / NULLIF((' + @right_sql + '), 0))';

        SET @p = @right_end;
    END

    SET @sql = @left_sql;
    SET @end_pos = @p;
    SET @ok = 1;
END
GO

-- ===========================================================================
-- expr := term (('+'|'-') term)*
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_pf_expr
    @formula VARCHAR(500),
    @pos     INT,
    @end_pos INT OUTPUT,
    @sql     VARCHAR(2000) OUTPUT,
    @ok      BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @len INT = LEN(@formula);
    DECLARE @left_sql VARCHAR(2000), @p INT;

    EXEC dbo.sp_pf_term @formula = @formula, @pos = @pos, @end_pos = @p OUTPUT, @sql = @left_sql OUTPUT, @ok = @ok OUTPUT;
    IF @ok = 0 BEGIN SET @end_pos = @p; RETURN; END

    WHILE 1 = 1
    BEGIN
        DECLARE @scan INT = @p;
        WHILE @scan <= @len AND SUBSTRING(@formula, @scan, 1) = ' ' SET @scan += 1;
        IF @scan > @len BREAK;
        DECLARE @op CHAR(1) = SUBSTRING(@formula, @scan, 1);
        IF @op <> '+' AND @op <> '-' BREAK;
        SET @scan += 1;

        DECLARE @right_sql VARCHAR(2000), @right_end INT, @right_ok BIT;
        EXEC dbo.sp_pf_term @formula = @formula, @pos = @scan, @end_pos = @right_end OUTPUT, @sql = @right_sql OUTPUT, @ok = @right_ok OUTPUT;
        IF @right_ok = 0 BEGIN SET @ok = 0; SET @end_pos = @right_end; RETURN; END

        SET @left_sql = '(' + @left_sql + ' ' + @op + ' ' + @right_sql + ')';
        SET @p = @right_end;
    END

    SET @sql = @left_sql;
    SET @end_pos = @p;
    SET @ok = 1;
END
GO

-- ===========================================================================
-- Top-level entry points: parse the ENTIRE string as one value expression,
-- or as one condition (tnai). Reject if any trailing content is left
-- unconsumed after the grammar matches a prefix -- a formula is valid only
-- if the whole string is a single well-formed expression/condition.
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_pf_parse_value
    @formula VARCHAR(500),
    @sql     VARCHAR(2000) OUTPUT,
    @ok      BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @end_pos INT;
    EXEC dbo.sp_pf_expr @formula = @formula, @pos = 1, @end_pos = @end_pos OUTPUT, @sql = @sql OUTPUT, @ok = @ok OUTPUT;
    IF @ok = 1
    BEGIN
        DECLARE @len INT = LEN(@formula);
        DECLARE @p INT = @end_pos;
        WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;
        IF @p <= @len SET @ok = 0;
    END
END
GO

CREATE OR ALTER PROCEDURE dbo.sp_pf_parse_condition
    @formula  VARCHAR(500),
    @left_sql VARCHAR(2000) OUTPUT,
    @op       VARCHAR(2) OUTPUT,
    @right_sql VARCHAR(2000) OUTPUT,
    @ok       BIT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @len INT = LEN(@formula);
    DECLARE @p INT;

    EXEC dbo.sp_pf_expr @formula = @formula, @pos = 1, @end_pos = @p OUTPUT, @sql = @left_sql OUTPUT, @ok = @ok OUTPUT;
    IF @ok = 0 RETURN;

    WHILE @p <= @len AND SUBSTRING(@formula, @p, 1) = ' ' SET @p += 1;

    DECLARE @two CHAR(2) = SUBSTRING(@formula, @p, 2);
    IF @two IN ('>=', '<=', '==', '!=')
    BEGIN
        SET @op = CASE @two WHEN '==' THEN '=' WHEN '!=' THEN '<>' ELSE @two END;
        SET @p += 2;
    END
    ELSE IF @p <= @len AND SUBSTRING(@formula, @p, 1) IN ('>', '<')
    BEGIN
        SET @op = SUBSTRING(@formula, @p, 1);
        SET @p += 1;
    END
    ELSE
    BEGIN
        SET @ok = 0;
        RETURN;
    END

    DECLARE @right_end INT;
    EXEC dbo.sp_pf_expr @formula = @formula, @pos = @p, @end_pos = @right_end OUTPUT, @sql = @right_sql OUTPUT, @ok = @ok OUTPUT;
    IF @ok = 0 RETURN;

    DECLARE @q INT = @right_end;
    WHILE @q <= @len AND SUBSTRING(@formula, @q, 1) = ' ' SET @q += 1;
    IF @q <= @len SET @ok = 0;
END
GO

-- ===========================================================================
-- Main engine entry point: reads @targil_id's formula, validates +
-- translates it via the recursive-descent parser above, executes the
-- resulting set-based query with sp_executesql, and logs timing/checksum.
-- ===========================================================================
CREATE OR ALTER PROCEDURE dbo.sp_calc_formula
    @targil_id    INT,
    @method       VARCHAR(50) = 'sql_sp',
    @persist_full BIT = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @targil VARCHAR(500), @tnai VARCHAR(500), @targil_false VARCHAR(500);
    SELECT @targil = targil, @tnai = tnai, @targil_false = targil_false
    FROM dbo.t_targil
    WHERE targil_id = @targil_id;

    IF @targil IS NULL
        THROW 50001, 'targil_id not found in t_targil', 1;

    DECLARE @t0 DATETIME2 = SYSUTCDATETIME();

    DECLARE @value_sql VARCHAR(2000), @value_ok BIT;
    EXEC dbo.sp_pf_parse_value @formula = @targil, @sql = @value_sql OUTPUT, @ok = @value_ok OUTPUT;
    IF @value_ok = 0
        THROW 50002, 'targil failed grammar validation -- rejected before reaching sp_executesql', 1;

    DECLARE @final_sql VARCHAR(4000);

    IF @tnai IS NULL
    BEGIN
        SET @final_sql = @value_sql;
    END
    ELSE
    BEGIN
        DECLARE @false_sql VARCHAR(2000), @false_ok BIT;
        EXEC dbo.sp_pf_parse_value @formula = @targil_false, @sql = @false_sql OUTPUT, @ok = @false_ok OUTPUT;
        IF @false_ok = 0
            THROW 50003, 'targil_false failed grammar validation', 1;

        DECLARE @cond_left VARCHAR(2000), @cond_op VARCHAR(2), @cond_right VARCHAR(2000), @cond_ok BIT;
        EXEC dbo.sp_pf_parse_condition @formula = @tnai, @left_sql = @cond_left OUTPUT, @op = @cond_op OUTPUT, @right_sql = @cond_right OUTPUT, @ok = @cond_ok OUTPUT;
        IF @cond_ok = 0
            THROW 50004, 'tnai failed grammar validation', 1;

        -- SEMANTICS.md section 5: if either side of the condition is itself
        -- NULL (a guarded sub-expression hit a domain error), the overall
        -- row is NULL -- checked explicitly first, since CASE WHEN treats
        -- NULL/UNKNOWN as false and would otherwise silently steer the row
        -- into the false branch.
        SET @final_sql =
            'CASE WHEN (' + @cond_left + ') IS NULL OR (' + @cond_right + ') IS NULL THEN NULL ' +
            'WHEN (' + @cond_left + ') ' + @cond_op + ' (' + @cond_right + ') THEN (' + @value_sql + ') ' +
            'ELSE (' + @false_sql + ') END';
    END

    DECLARE @compile_ms FLOAT = DATEDIFF(MICROSECOND, @t0, SYSUTCDATETIME()) / 1000.0;

    -- eval phase: full-dataset checksum + null_count (SEMANTICS.md section 7)
    DECLARE @t1 DATETIME2 = SYSUTCDATETIME();
    DECLARE @checksum FLOAT, @null_count INT, @rows_processed INT;
    DECLARE @eval_sql NVARCHAR(4000) = N'
        SELECT @checksum_out = SUM(result),
               @null_count_out = SUM(CASE WHEN result IS NULL THEN 1 ELSE 0 END),
               @rows_out = COUNT(*)
        FROM (SELECT ' + @final_sql + N' AS result FROM dbo.t_data) AS calc';
    EXEC sp_executesql
        @eval_sql,
        N'@checksum_out FLOAT OUTPUT, @null_count_out INT OUTPUT, @rows_out INT OUTPUT',
        @checksum_out = @checksum OUTPUT, @null_count_out = @null_count OUTPUT, @rows_out = @rows_processed OUTPUT;
    DECLARE @eval_ms FLOAT = DATEDIFF(MICROSECOND, @t1, SYSUTCDATETIME()) / 1000.0;

    -- persist phase: sample (or full) write to t_results. NOTE: this
    -- re-scans/re-evaluates the guarded expression rather than reusing the
    -- checksum query's result set (no session-scoped cached derived table
    -- between statements in T-SQL) -- unlike the other four engines, this
    -- method's eval_ms/persist_ms are not a clean decomposition of one
    -- shared compute pass. Documented in REPORT.md per the brief.
    DECLARE @t2 DATETIME2 = SYSUTCDATETIME();
    IF @persist_full = 1
    BEGIN
        DECLARE @persist_full_sql NVARCHAR(4000) = N'
            INSERT INTO dbo.t_results (data_id, targil_id, method, result)
            SELECT data_id, @targil_id_p, @method_p, ' + @final_sql + N'
            FROM dbo.t_data';
        EXEC sp_executesql
            @persist_full_sql,
            N'@targil_id_p INT, @method_p VARCHAR(50)',
            @targil_id_p = @targil_id, @method_p = @method;
    END
    ELSE
    BEGIN
        DECLARE @persist_sample_sql NVARCHAR(4000) = N'
            INSERT INTO dbo.t_results (data_id, targil_id, method, result)
            SELECT d.data_id, @targil_id_p, @method_p, ' + @final_sql + N'
            FROM dbo.t_data d
            JOIN dbo.t_sample s ON s.data_id = d.data_id';
        EXEC sp_executesql
            @persist_sample_sql,
            N'@targil_id_p INT, @method_p VARCHAR(50)',
            @targil_id_p = @targil_id, @method_p = @method;
    END
    DECLARE @persist_ms FLOAT = DATEDIFF(MICROSECOND, @t2, SYSUTCDATETIME()) / 1000.0;

    DECLARE @run_time FLOAT = @compile_ms + @eval_ms + @persist_ms;

    INSERT INTO dbo.t_log (targil_id, method, run_time, rows_processed, compile_ms, eval_ms, persist_ms, checksum, null_count)
    VALUES (@targil_id, @method, @run_time, @rows_processed, @compile_ms, @eval_ms, @persist_ms, @checksum, @null_count);

    SELECT
        @targil_id AS targil_id, @compile_ms AS compile_ms, @eval_ms AS eval_ms, @persist_ms AS persist_ms,
        @checksum AS checksum, @null_count AS null_count, @rows_processed AS rows_processed;
END
GO
