using System.Data;
using System.Diagnostics;
using Microsoft.Data.SqlClient;

namespace PaymentSystem.Shared;

/// <summary>
/// Shared data access + Step 6 persistence strategy for the C# engines --
/// the C# counterpart of src/python/persistence.py. Same contract: compute
/// over all 1,000,000 rows always, persist only the deterministic
/// 10,000-row sample from dbo.t_sample (plus the full-dataset checksum/
/// null_count in t_log), with a full-dump path for --persist=full.
/// </summary>
public static class Db
{
    public const int TotalRows = 1_000_000;

    public static SqlConnection Connect()
    {
        var conn = new SqlConnection(Config.ConnectionString);
        conn.Open();
        return conn;
    }

    public static List<Formula> FetchFormulas(SqlConnection conn)
    {
        var result = new List<Formula>();
        using var cmd = new SqlCommand("SELECT targil_id, targil, tnai, targil_false FROM dbo.t_targil ORDER BY targil_id", conn);
        using var reader = cmd.ExecuteReader();
        while (reader.Read())
        {
            result.Add(new Formula(
                reader.GetInt32(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3)));
        }
        return result;
    }

    /// <summary>Loads all of t_data once, ordered by data_id (so data_id
    /// value `did` sits at array index `did - 1`). Outside any per-formula
    /// timing -- a fixed setup cost shared by every formula.</summary>
    public static (int[] DataId, double[] A, double[] B, double[] C, double[] D) FetchAllData(SqlConnection conn)
    {
        var dataId = new int[TotalRows];
        var a = new double[TotalRows];
        var b = new double[TotalRows];
        var c = new double[TotalRows];
        var d = new double[TotalRows];

        using var cmd = new SqlCommand("SELECT data_id, a, b, c, d FROM dbo.t_data ORDER BY data_id", conn);
        using var reader = cmd.ExecuteReader();
        var i = 0;
        while (reader.Read())
        {
            dataId[i] = reader.GetInt32(0);
            a[i] = reader.GetDouble(1);
            b[i] = reader.GetDouble(2);
            c[i] = reader.GetDouble(3);
            d[i] = reader.GetDouble(4);
            i++;
        }
        return (dataId, a, b, c, d);
    }

    /// <summary>The shared 10,000-id sample every engine persists results
    /// for -- see dbo.t_sample (sql/01_schema.sql) and
    /// persistence.sample_data_ids() (generated once, in Python).</summary>
    public static int[] FetchSampleIds(SqlConnection conn)
    {
        var ids = new List<int>(10_000);
        using var cmd = new SqlCommand("SELECT data_id FROM dbo.t_sample ORDER BY data_id", conn);
        using var reader = cmd.ExecuteReader();
        while (reader.Read()) ids.Add(reader.GetInt32(0));
        return [.. ids];
    }

    public static void WriteLog(
        SqlConnection conn, int targilId, string method, double runTime, int rowsProcessed,
        double compileMs, double evalMs, double persistMs, double? checksum, int nullCount)
    {
        using var cmd = new SqlCommand(
            """
            INSERT INTO dbo.t_log
                (targil_id, method, run_time, rows_processed, compile_ms, eval_ms, persist_ms, checksum, null_count)
            VALUES (@targil_id, @method, @run_time, @rows_processed, @compile_ms, @eval_ms, @persist_ms, @checksum, @null_count)
            """, conn);
        cmd.Parameters.AddWithValue("@targil_id", targilId);
        cmd.Parameters.AddWithValue("@method", method);
        cmd.Parameters.AddWithValue("@run_time", runTime);
        cmd.Parameters.AddWithValue("@rows_processed", rowsProcessed);
        cmd.Parameters.AddWithValue("@compile_ms", compileMs);
        cmd.Parameters.AddWithValue("@eval_ms", evalMs);
        cmd.Parameters.AddWithValue("@persist_ms", persistMs);
        cmd.Parameters.AddWithValue("@checksum", (object?)checksum ?? DBNull.Value);
        cmd.Parameters.AddWithValue("@null_count", nullCount);
        cmd.ExecuteNonQuery();
    }

    private static DataTable ResultsTable()
    {
        var t = new DataTable();
        t.Columns.Add("data_id", typeof(int));
        t.Columns.Add("targil_id", typeof(int));
        t.Columns.Add("method", typeof(string));
        t.Columns.Add("result", typeof(double));
        return t;
    }

    private static double BulkWrite(SqlConnection conn, DataTable table)
    {
        var sw = Stopwatch.StartNew();
        using var bulk = new SqlBulkCopy(conn) { DestinationTableName = "dbo.t_results", BatchSize = 100_000 };
        bulk.ColumnMappings.Add("data_id", "data_id");
        bulk.ColumnMappings.Add("targil_id", "targil_id");
        bulk.ColumnMappings.Add("method", "method");
        bulk.ColumnMappings.Add("result", "result");
        bulk.WriteToServer(table);
        return sw.Elapsed.TotalMilliseconds;
    }

    /// <summary>Writes the deterministic 10,000-row sample via SqlBulkCopy.
    /// results[did - 1] is the value for data_id `did` (null = NULL).
    /// Returns elapsed persist time in ms.</summary>
    public static double WriteResultsSample(SqlConnection conn, int targilId, string method, int[] sampleIds, double?[] results)
    {
        var table = ResultsTable();
        foreach (var did in sampleIds)
        {
            var row = table.NewRow();
            row["data_id"] = did;
            row["targil_id"] = targilId;
            row["method"] = method;
            row["result"] = (object?)results[did - 1] ?? DBNull.Value;
            table.Rows.Add(row);
        }
        return BulkWrite(conn, table);
    }

    /// <summary>--persist=full: writes all 1,000,000 rows via SqlBulkCopy.
    /// Returns elapsed persist time in ms.</summary>
    public static double WriteResultsFull(SqlConnection conn, int targilId, string method, int[] dataId, double?[] results)
    {
        var table = ResultsTable();
        for (var i = 0; i < dataId.Length; i++)
        {
            var row = table.NewRow();
            row["data_id"] = dataId[i];
            row["targil_id"] = targilId;
            row["method"] = method;
            row["result"] = (object?)results[i] ?? DBNull.Value;
            table.Rows.Add(row);
        }
        return BulkWrite(conn, table);
    }
}
