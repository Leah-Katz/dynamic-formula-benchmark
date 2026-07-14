// DataTableCompute -- the naive baseline the assignment explicitly suggests
// (System.Data.DataTable / DataColumn.Expression). Expect it to be slow --
// that's the point of including it -- AND, as it turns out, expressively
// incomplete: DataColumn.Expression has no Sqrt/Log/Pow, so formulas that
// need them are skipped with an explicit, logged reason rather than faked.
// See DataColumnExpressionEmitter.cs for the full explanation.
//
// Usage: dotnet run --project src/dotnet/DataTableCompute -- [--persist=full]

using System.Data;
using System.Diagnostics;
using DataTableCompute;
using PaymentSystem.Shared;

const string Method = "dotnet_datatable";
var persistFull = args.Contains("--persist=full");

using var conn = Db.Connect();
var formulas = Db.FetchFormulas(conn);
Console.WriteLine($"Loading {Db.TotalRows:N0} rows of t_data...");
var (dataId, a, b, c, d) = Db.FetchAllData(conn);
var sampleIds = Db.FetchSampleIds(conn);

Console.WriteLine($"[{Method}] evaluating {formulas.Count} formulas x {dataId.Length:N0} rows (persist={(persistFull ? "full" : "sample")})");

var source = new DataTable();
source.Columns.Add("a", typeof(double));
source.Columns.Add("b", typeof(double));
source.Columns.Add("c", typeof(double));
source.Columns.Add("d", typeof(double));
source.BeginLoadData();
for (var i = 0; i < dataId.Length; i++)
    source.Rows.Add(a[i], b[i], c[i], d[i]);
source.EndLoadData();

var overallSw = Stopwatch.StartNew();
var skipped = new List<(int TargilId, string Reason)>();

foreach (var formula in formulas)
{
    var compileSw = Stopwatch.StartNew();
    string finalExpr;
    try
    {
        var valueNode = FormulaParser.ParseValue(formula.Targil);
        if (formula.IsConditional)
        {
            var falseNode = FormulaParser.ParseValue(formula.TargilFalse!);
            var condNode = FormulaParser.ParseCondition(formula.Tnai!);
            var valueExpr = DataColumnExpressionEmitter.EmitValue(valueNode);
            var falseExpr = DataColumnExpressionEmitter.EmitValue(falseNode);
            var (condLeft, condOp, condRight) = DataColumnExpressionEmitter.EmitCondition(condNode);
            finalExpr = $"IIF(({condLeft}) {condOp} ({condRight}), ({valueExpr}), ({falseExpr}))";
        }
        else
        {
            finalExpr = DataColumnExpressionEmitter.EmitValue(valueNode);
        }
    }
    catch (NotSupportedByDataTableComputeException ex)
    {
        skipped.Add((formula.TargilId, ex.Message));
        Console.WriteLine($"  targil {formula.TargilId,2}: SKIPPED -- {ex.Message}");
        continue;
    }
    var compileMs = compileSw.Elapsed.TotalMilliseconds;

    var evalSw = Stopwatch.StartNew();
    var col = new DataColumn("computed", typeof(double), finalExpr);
    source.Columns.Add(col);

    var results = new double?[dataId.Length];
    for (var i = 0; i < dataId.Length; i++)
    {
        var raw = source.Rows[i][col];
        var v = raw is DBNull ? double.NaN : Convert.ToDouble(raw);
        results[i] = double.IsNaN(v) || double.IsInfinity(v) ? null : v;
    }
    source.Columns.Remove(col);
    var evalMs = evalSw.Elapsed.TotalMilliseconds;

    var nullCount = results.Count(r => r is null);
    var checksum = results.Where(r => r.HasValue).Sum(r => r!.Value);

    double persistMs;
    if (persistFull)
    {
        persistMs = Db.WriteResultsFull(conn, formula.TargilId, Method, dataId, results);
    }
    else
    {
        persistMs = Db.WriteResultsSample(conn, formula.TargilId, Method, sampleIds, results);
    }

    var runTime = compileMs + evalMs + persistMs;
    Db.WriteLog(conn, formula.TargilId, Method, runTime, dataId.Length, compileMs, evalMs, persistMs, checksum, nullCount);

    Console.WriteLine(
        $"  targil {formula.TargilId,2}: compile={compileMs,8:F2}ms  eval={evalMs,9:F2}ms  " +
        $"persist={persistMs,8:F2}ms  nulls={nullCount,7}  checksum={checksum:F6}");
}

Console.WriteLine($"[{Method}] done in {overallSw.Elapsed.TotalSeconds:F2}s");
if (skipped.Count > 0)
{
    Console.WriteLine($"[{Method}] {skipped.Count} formula(s) skipped -- DataColumn.Expression cannot express them (see REPORT.md):");
    foreach (var (id, reason) in skipped)
        Console.WriteLine($"    targil {id}: {reason}");
}
