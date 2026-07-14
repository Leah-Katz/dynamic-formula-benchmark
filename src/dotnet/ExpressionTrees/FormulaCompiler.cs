using System.Linq.Expressions;
using PaymentSystem.Shared;

namespace ExpressionTrees;

/// <summary>
/// Walks a validated FormulaNode (PaymentSystem.Shared.FormulaParser) and
/// compiles it ONCE into a Func&lt;double,double,double,double,double?&gt;
/// delegate (params a,b,c,d) -- the "compile once, execute a million times"
/// strategy. Domain-error handling matches SEMANTICS.md's C# guidance
/// exactly: unlike T-SQL, plain IEEE-754 double arithmetic in C# never
/// throws for these operations (Math.Sqrt/Math.Log of an invalid argument
/// return NaN, division by zero returns +/-Infinity, Math.Pow likewise), so
/// no per-operation guards are needed -- a single double.IsNaN/IsInfinity
/// check on the final result, inserted once at compile time, is sufficient
/// and is inserted around every value sub-expression (see BuildGuardedValue).
/// </summary>
public static class FormulaCompiler
{
    public static Func<double, double, double, double, double?> Compile(Formula formula)
    {
        var pa = Expression.Parameter(typeof(double), "a");
        var pb = Expression.Parameter(typeof(double), "b");
        var pc = Expression.Parameter(typeof(double), "c");
        var pd = Expression.Parameter(typeof(double), "d");
        var vars = new Vars(pa, pb, pc, pd);

        Expression<Func<double, double, double, double, double?>> lambda;

        if (!formula.IsConditional)
        {
            var valueNode = FormulaParser.ParseValue(formula.Targil);
            var body = BuildGuardedValue(valueNode, vars);
            lambda = Expression.Lambda<Func<double, double, double, double, double?>>(body, pa, pb, pc, pd);
        }
        else
        {
            var valueNode = FormulaParser.ParseValue(formula.Targil);
            var falseNode = FormulaParser.ParseValue(formula.TargilFalse!);
            var cond = FormulaParser.ParseCondition(formula.Tnai!);

            var leftVar = Expression.Variable(typeof(double), "condLeft");
            var rightVar = Expression.Variable(typeof(double), "condRight");
            var condInvalid = Expression.OrElse(IsBad(leftVar), IsBad(rightVar));
            var compareExpr = BuildCompare(cond.Op, leftVar, rightVar);

            // SEMANTICS.md section 5: if either side of the condition is
            // itself undefined, the overall row is NULL -- checked before
            // the comparison, never silently falling through to the false
            // branch (NaN comparisons are all false in IEEE-754).
            var body = Expression.Block(
                [leftVar, rightVar],
                Expression.Assign(leftVar, BuildRaw(cond.Left, vars)),
                Expression.Assign(rightVar, BuildRaw(cond.Right, vars)),
                Expression.Condition(
                    condInvalid,
                    Expression.Constant(null, typeof(double?)),
                    Expression.Condition(compareExpr, BuildGuardedValue(valueNode, vars), BuildGuardedValue(falseNode, vars))));

            lambda = Expression.Lambda<Func<double, double, double, double, double?>>(body, pa, pb, pc, pd);
        }

        return lambda.Compile();
    }

    private readonly record struct Vars(ParameterExpression A, ParameterExpression B, ParameterExpression C, ParameterExpression D);

    /// <summary>Raw double sub-expression (unguarded, per SEMANTICS.md the
    /// guard only needs to apply once at the end of a value expression).</summary>
    private static Expression BuildRaw(FormulaNode node, Vars v) => node switch
    {
        NumberNode n => Expression.Constant(n.Value),
        VarNode { Name: "a" } => v.A,
        VarNode { Name: "b" } => v.B,
        VarNode { Name: "c" } => v.C,
        VarNode { Name: "d" } => v.D,
        VarNode vn => throw new InvalidOperationException($"unknown var {vn.Name}"),
        UnaryMinusNode u => Expression.Negate(BuildRaw(u.Operand, v)),
        BinaryOpNode b => b.Op switch
        {
            '+' => Expression.Add(BuildRaw(b.Left, v), BuildRaw(b.Right, v)),
            '-' => Expression.Subtract(BuildRaw(b.Left, v), BuildRaw(b.Right, v)),
            '*' => Expression.Multiply(BuildRaw(b.Left, v), BuildRaw(b.Right, v)),
            '/' => Expression.Divide(BuildRaw(b.Left, v), BuildRaw(b.Right, v)),
            _ => throw new InvalidOperationException($"unknown operator {b.Op}"),
        },
        PowerNode p => Expression.Call(PowMethod, BuildRaw(p.Base, v), BuildRaw(p.Exponent, v)),
        FuncCallNode f => f.Name switch
        {
            "sqrt" => Expression.Call(SqrtMethod, BuildRaw(f.Args[0], v)),
            "log" => Expression.Call(LogMethod, BuildRaw(f.Args[0], v)),
            "abs" => Expression.Call(AbsMethod, BuildRaw(f.Args[0], v)),
            "min" => Expression.Call(MinMethod, BuildRaw(f.Args[0], v), BuildRaw(f.Args[1], v)),
            "max" => Expression.Call(MaxMethod, BuildRaw(f.Args[0], v), BuildRaw(f.Args[1], v)),
            "pow" => Expression.Call(PowMethod, BuildRaw(f.Args[0], v), BuildRaw(f.Args[1], v)),
            _ => throw new InvalidOperationException($"unknown function {f.Name}"),
        },
        _ => throw new InvalidOperationException($"unhandled node {node.GetType().Name}"),
    };

    /// <summary>Wraps a value sub-expression with the catch-all domain-error
    /// guard (SEMANTICS.md section 4): NaN/Infinity -> NULL.</summary>
    private static Expression BuildGuardedValue(FormulaNode node, Vars v)
    {
        var raw = BuildRaw(node, v);
        var resultVar = Expression.Variable(typeof(double), "result");
        return Expression.Block(
            typeof(double?),
            [resultVar],
            Expression.Assign(resultVar, raw),
            Expression.Condition(
                IsBad(resultVar),
                Expression.Constant(null, typeof(double?)),
                Expression.Convert(resultVar, typeof(double?))));
    }

    private static Expression IsBad(Expression d) =>
        Expression.OrElse(Expression.Call(IsNaNMethod, d), Expression.Call(IsInfinityMethod, d));

    private static Expression BuildCompare(string op, Expression left, Expression right) => op switch
    {
        ">" => Expression.GreaterThan(left, right),
        "<" => Expression.LessThan(left, right),
        ">=" => Expression.GreaterThanOrEqual(left, right),
        "<=" => Expression.LessThanOrEqual(left, right),
        "==" => Expression.Equal(left, right),
        "!=" => Expression.NotEqual(left, right),
        _ => throw new InvalidOperationException($"unknown comparison operator {op}"),
    };

    private static readonly System.Reflection.MethodInfo SqrtMethod = ((Func<double, double>)Math.Sqrt).Method;
    private static readonly System.Reflection.MethodInfo LogMethod = ((Func<double, double>)Math.Log).Method;
    private static readonly System.Reflection.MethodInfo AbsMethod = ((Func<double, double>)Math.Abs).Method;
    private static readonly System.Reflection.MethodInfo MinMethod = ((Func<double, double, double>)Math.Min).Method;
    private static readonly System.Reflection.MethodInfo MaxMethod = ((Func<double, double, double>)Math.Max).Method;
    private static readonly System.Reflection.MethodInfo PowMethod = ((Func<double, double, double>)Math.Pow).Method;
    private static readonly System.Reflection.MethodInfo IsNaNMethod = ((Func<double, bool>)double.IsNaN).Method;
    private static readonly System.Reflection.MethodInfo IsInfinityMethod = ((Func<double, bool>)double.IsInfinity).Method;
}
