using System.Globalization;

namespace PaymentSystem.Shared;

/// <summary>
/// Recursive-descent parser for the SEMANTICS.md grammar, the C# sibling of
/// formula_parser.py (AST walk) and sql/02_sp_calc_formula.sql's sp_pf_*
/// procedures (T-SQL recursive descent). Formula strings come from
/// t_targil, i.e. from outside this program's trust boundary -- this
/// parser IS the validation: anything outside the grammar fails to parse
/// and raises FormulaValidationException before any emitter ever sees it.
/// Whitelist: identifiers a/b/c/d, functions sqrt/log/abs/min/max/pow,
/// operators + - * / ^, comparisons (condition only) > &lt; &gt;= &lt;= == !=.
/// </summary>
public static class FormulaParser
{
    private static readonly HashSet<string> AllowedVars = ["a", "b", "c", "d"];
    private static readonly HashSet<string> Func1 = ["sqrt", "log", "abs"];
    private static readonly HashSet<string> Func2 = ["min", "max", "pow"];

    public static FormulaNode ParseValue(string formula)
    {
        var p = new Parser(formula);
        var node = p.ParseExpr();
        p.ExpectEnd();
        return node;
    }

    public static ConditionNode ParseCondition(string formula)
    {
        var p = new Parser(formula);
        var left = p.ParseExpr();
        var op = p.ParseCompareOp();
        var right = p.ParseExpr();
        p.ExpectEnd();
        return new ConditionNode(left, op, right);
    }

    private sealed class Parser(string s)
    {
        private readonly string _s = s;
        private int _pos;

        public void ExpectEnd()
        {
            SkipWs();
            if (_pos != _s.Length)
                throw new FormulaValidationException($"unexpected trailing content at position {_pos} in '{_s}'");
        }

        private void SkipWs()
        {
            while (_pos < _s.Length && _s[_pos] == ' ') _pos++;
        }

        private char Peek()
        {
            SkipWs();
            return _pos < _s.Length ? _s[_pos] : '\0';
        }

        public string ParseCompareOp()
        {
            SkipWs();
            if (_pos + 1 < _s.Length)
            {
                var two = _s.Substring(_pos, 2);
                if (two is ">=" or "<=" or "==" or "!=")
                {
                    _pos += 2;
                    return two switch { "==" => "==", "!=" => "!=", _ => two };
                }
            }
            if (_pos < _s.Length && (_s[_pos] == '>' || _s[_pos] == '<'))
            {
                var op = _s[_pos].ToString();
                _pos += 1;
                return op;
            }
            throw new FormulaValidationException($"expected a comparison operator at position {_pos} in '{_s}'");
        }

        // expr := term (('+' | '-') term)*
        public FormulaNode ParseExpr()
        {
            var left = ParseTerm();
            while (true)
            {
                var c = Peek();
                if (c != '+' && c != '-') break;
                _pos++;
                var right = ParseTerm();
                left = new BinaryOpNode(c, left, right);
            }
            return left;
        }

        // term := unary (('*' | '/') unary)*
        private FormulaNode ParseTerm()
        {
            var left = ParseUnary();
            while (true)
            {
                var c = Peek();
                if (c != '*' && c != '/') break;
                _pos++;
                var right = ParseUnary();
                left = new BinaryOpNode(c, left, right);
            }
            return left;
        }

        // unary := '-' unary | power
        private FormulaNode ParseUnary()
        {
            if (Peek() == '-')
            {
                _pos++;
                return new UnaryMinusNode(ParseUnary());
            }
            return ParsePower();
        }

        // power := atom ('^' unary)?     -- right-associative
        private FormulaNode ParsePower()
        {
            var baseNode = ParseAtom();
            if (Peek() == '^')
            {
                _pos++;
                var exp = ParseUnary();
                return new PowerNode(baseNode, exp);
            }
            return baseNode;
        }

        // atom := NUMBER | IDENTIFIER | FUNC1'('expr')' | FUNC2'('expr','expr')' | '('expr')'
        private FormulaNode ParseAtom()
        {
            SkipWs();
            if (_pos >= _s.Length)
                throw new FormulaValidationException($"unexpected end of formula '{_s}'");

            var c = _s[_pos];

            if (char.IsDigit(c) || c == '.')
            {
                var start = _pos;
                var dotSeen = false;
                while (_pos < _s.Length && (char.IsDigit(_s[_pos]) || (_s[_pos] == '.' && !dotSeen)))
                {
                    if (_s[_pos] == '.') dotSeen = true;
                    _pos++;
                }
                var text = _s.Substring(start, _pos - start);
                if (text == ".")
                    throw new FormulaValidationException($"invalid number literal at position {start} in '{_s}'");
                return new NumberNode(double.Parse(text, CultureInfo.InvariantCulture));
            }

            if (c is >= 'a' and <= 'z')
            {
                var start = _pos;
                while (_pos < _s.Length && _s[_pos] is >= 'a' and <= 'z') _pos++;
                var word = _s.Substring(start, _pos - start);

                if (AllowedVars.Contains(word))
                    return new VarNode(word);

                if (Func1.Contains(word) || Func2.Contains(word))
                {
                    SkipWs();
                    Expect('(');
                    var arg1 = ParseExpr();
                    FormulaNode[] args;
                    if (Func2.Contains(word))
                    {
                        SkipWs();
                        Expect(',');
                        var arg2 = ParseExpr();
                        SkipWs();
                        Expect(')');
                        args = [arg1, arg2];
                    }
                    else
                    {
                        SkipWs();
                        Expect(')');
                        args = [arg1];
                    }
                    return new FuncCallNode(word, args);
                }

                throw new FormulaValidationException($"identifier/function not allowed: '{word}' in '{_s}'");
            }

            if (c == '(')
            {
                _pos++;
                var inner = ParseExpr();
                SkipWs();
                Expect(')');
                return inner;
            }

            throw new FormulaValidationException($"unexpected character '{c}' at position {_pos} in '{_s}'");
        }

        private void Expect(char c)
        {
            if (_pos >= _s.Length || _s[_pos] != c)
                throw new FormulaValidationException($"expected '{c}' at position {_pos} in '{_s}'");
            _pos++;
        }
    }
}
