namespace PaymentSystem.Shared;

public sealed record Formula(int TargilId, string Targil, string? Tnai, string? TargilFalse)
{
    public bool IsConditional => Tnai is not null;
}
