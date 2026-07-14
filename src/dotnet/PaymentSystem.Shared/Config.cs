namespace PaymentSystem.Shared;

/// <summary>
/// Single source of truth for the database connection string used by every
/// C# engine (DataTableCompute, ExpressionTrees) -- the C# counterpart of
/// config.py. Override via PAYMENTSYSTEM_CONNECTION_STRING_DOTNET (ADO.NET
/// connection-string syntax differs from the Python engines' ODBC syntax,
/// hence a separate env var), otherwise falls back to a local Windows-auth
/// default matching the same SQL Server 2025 instance.
/// </summary>
public static class Config
{
    public static string ConnectionString =>
        Environment.GetEnvironmentVariable("PAYMENTSYSTEM_CONNECTION_STRING_DOTNET")
        ?? "Server=localhost;Database=PaymentSystem;Trusted_Connection=True;TrustServerCertificate=True;";
}
