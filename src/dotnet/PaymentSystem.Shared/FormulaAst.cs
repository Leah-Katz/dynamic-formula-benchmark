namespace PaymentSystem.Shared;

/// <summary>
/// AST for the SEMANTICS.md grammar -- the C# counterpart of
/// formula_parser.py's validated ast.Expression. Produced once by
/// FormulaParser.Parse*, then walked by each engine's own emitter
/// (DataColumnExpressionEmitter for DataTableCompute,
/// ExpressionTreeEmitter for ExpressionTrees) -- same "validate once,
/// emit per target" shape as the Python parser's to_numpy_expr().
/// </summary>
public abstract record FormulaNode;

public sealed record NumberNode(double Value) : FormulaNode;

/// <summary>One of the four whitelisted identifiers: a, b, c, d.</summary>
public sealed record VarNode(string Name) : FormulaNode;

public sealed record UnaryMinusNode(FormulaNode Operand) : FormulaNode;

/// <summary>Op is one of '+', '-', '*', '/'.</summary>
public sealed record BinaryOpNode(char Op, FormulaNode Left, FormulaNode Right) : FormulaNode;

/// <summary>x ^ y (exponentiation, never XOR).</summary>
public sealed record PowerNode(FormulaNode Base, FormulaNode Exponent) : FormulaNode;

/// <summary>One of sqrt/log/abs (1 arg) or min/max/pow (2 args).</summary>
public sealed record FuncCallNode(string Name, FormulaNode[] Args) : FormulaNode;

/// <summary>tnai only: exactly one comparison between two value expressions.
/// Op is one of '>','<','>=','<=','==','!='.</summary>
public sealed record ConditionNode(FormulaNode Left, string Op, FormulaNode Right);

public sealed class FormulaValidationException(string message) : Exception(message);
