using System.Globalization;
using PaymentSystem.Shared;

namespace DataTableCompute;

/// <summary>
/// Walks a validated FormulaNode (see PaymentSystem.Shared.FormulaParser)
/// and emits a System.Data DataColumn.Expression string.
///
/// ADO.NET's DataColumn.Expression syntax is genuinely more limited than it
/// looks: Abs/Min/Max/Sum/Avg/StDev/Var are AGGREGATE functions only (they
/// operate over a set of rows, e.g. a parent/child relation, not
/// element-wise per row -- calling Abs(a) on a plain column silently
/// returns DBNull for every row, it does not throw). There is no Sqrt, Log,
/// or Pow/'^' at all. Verified directly against this .NET 10 runtime before
/// writing this emitter (see commit history / REPORT.md) rather than
/// assumed from documentation.
///
/// Workarounds used where the grammar's own arithmetic already covers it:
///   abs(x)   -> IIF((x) &lt; 0, -(x), (x))
///   min(x,y) -> IIF((x) &gt; (y), (y), (x))
///   max(x,y) -> IIF((x) &gt; (y), (x), (y))
///   x^2 / pow(x,2) -> (x) * (x)   -- exact, not an approximation, and
///                      covers every exponent actually used in the catalog
///
/// sqrt(...), log(...), and any pow/^ with a non-literal-2 exponent have no
/// arithmetic workaround and throw NotSupportedByDataTableComputeException
/// -- the engine driver catches this per formula, skips it, and records why
/// rather than silently faking an unsupported computation. See REPORT.md.
/// </summary>
public sealed class NotSupportedByDataTableComputeException(string reason) : Exception(reason);

public static class DataColumnExpressionEmitter
{
    public static string EmitValue(FormulaNode node) => Emit(node);

    public static (string Left, string Op, string Right) EmitCondition(ConditionNode cond)
    {
        var opSql = cond.Op switch
        {
            "==" => "=",
            "!=" => "<>",
            var op => op,
        };
        return (Emit(cond.Left), opSql, Emit(cond.Right));
    }

    private static string Emit(FormulaNode node) => node switch
    {
        NumberNode n => n.Value.ToString(CultureInfo.InvariantCulture),
        VarNode v => v.Name,
        UnaryMinusNode u => $"(-({Emit(u.Operand)}))",
        BinaryOpNode b => $"({Emit(b.Left)} {b.Op} {Emit(b.Right)})",
        PowerNode p => EmitPower(p),
        FuncCallNode f => EmitFuncCall(f),
        _ => throw new NotSupportedException($"unhandled node type {node.GetType().Name}"),
    };

    private static string EmitPower(PowerNode p)
    {
        if (p.Exponent is NumberNode { Value: 2.0 })
        {
            var b = Emit(p.Base);
            return $"({b} * {b})";
        }
        throw new NotSupportedByDataTableComputeException(
            "DataColumn.Expression has no Pow()/'^' operator -- only x^2 (translated to x*x) is supported, not this exponent");
    }

    private static string EmitFuncCall(FuncCallNode f) => f.Name switch
    {
        "abs" => $"IIF(({Emit(f.Args[0])}) < 0, -({Emit(f.Args[0])}), ({Emit(f.Args[0])}))",
        "min" => $"IIF(({Emit(f.Args[0])}) > ({Emit(f.Args[1])}), ({Emit(f.Args[1])}), ({Emit(f.Args[0])}))",
        "max" => $"IIF(({Emit(f.Args[0])}) > ({Emit(f.Args[1])}), ({Emit(f.Args[0])}), ({Emit(f.Args[1])}))",
        "pow" when f.Args[1] is NumberNode { Value: 2.0 } => $"(({Emit(f.Args[0])}) * ({Emit(f.Args[0])}))",
        "pow" => throw new NotSupportedByDataTableComputeException(
            "DataColumn.Expression has no Pow() function -- only pow(x,2) (translated to x*x) is supported"),
        "sqrt" => throw new NotSupportedByDataTableComputeException(
            "DataColumn.Expression has no Sqrt() function (Sqrt() is an aggregate-only identifier here and does not exist as an element-wise function)"),
        "log" => throw new NotSupportedByDataTableComputeException(
            "DataColumn.Expression has no Log() function"),
        _ => throw new NotSupportedException($"unhandled function {f.Name}"),
    };
}
