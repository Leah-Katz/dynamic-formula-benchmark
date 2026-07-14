// ExpressionTrees -- parse each formula ONCE into a System.Linq.Expressions
// tree, compile it to a cached Func<double,double,double,double,double?>
// delegate, then run that delegate over all 1,000,000 rows. Expect this to
// be dramatically faster than DataTableCompute (no re-parsing per row) and
// competitive with (or faster than) the JIT-compiled path Python's eval()
// baseline lacks entirely.
//
// Usage: dotnet run --project src/dotnet/ExpressionTrees -- [--persist=full]

using System.Diagnostics;
using ExpressionTrees;
using PaymentSystem.Shared;

const string Method = "dotnet_exprtree";
var persistFull = args.Contains("--persist=full");

using var conn = Db.Connect();
var formulas = Db.FetchFormulas(conn);
Console.WriteLine($"Loading {Db.TotalRows:N0} rows of t_data...");
var (dataId, a, b, c, d) = Db.FetchAllData(conn);
var sampleIds = Db.FetchSampleIds(conn);

Console.WriteLine($"[{Method}] evaluating {formulas.Count} formulas x {dataId.Length:N0} rows (persist={(persistFull ? "full" : "sample")})");

var overallSw = Stopwatch.StartNew();

foreach (var formula in formulas)
{
    var compileSw = Stopwatch.StartNew();
    var fn = FormulaCompiler.Compile(formula);
    var compileMs = compileSw.Elapsed.TotalMilliseconds;

    var evalSw = Stopwatch.StartNew();
    var results = new double?[dataId.Length];
    for (var i = 0; i < dataId.Length; i++)
        results[i] = fn(a[i], b[i], c[i], d[i]);
    var evalMs = evalSw.Elapsed.TotalMilliseconds;

    var nullCount = results.Count(r => r is null);
    var checksum = results.Where(r => r.HasValue).Sum(r => r!.Value);

    double persistMs = persistFull
        ? Db.WriteResultsFull(conn, formula.TargilId, Method, dataId, results)
        : Db.WriteResultsSample(conn, formula.TargilId, Method, sampleIds, results);

    var runTime = compileMs + evalMs + persistMs;
    Db.WriteLog(conn, formula.TargilId, Method, runTime, dataId.Length, compileMs, evalMs, persistMs, checksum, nullCount);

    Console.WriteLine(
        $"  targil {formula.TargilId,2}: compile={compileMs,8:F3}ms  eval={evalMs,9:F3}ms  " +
        $"persist={persistMs,8:F2}ms  nulls={nullCount,7}  checksum={checksum:F6}");
}

Console.WriteLine($"[{Method}] done in {overallSw.Elapsed.TotalSeconds:F2}s");
