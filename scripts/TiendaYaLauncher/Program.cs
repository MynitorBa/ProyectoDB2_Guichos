using System.Diagnostics;

var directory = new DirectoryInfo(AppContext.BaseDirectory);
string? scriptsDirectory = null;
while (directory is not null)
{
    var candidate = Path.Combine(directory.FullName, "scripts");
    if (File.Exists(Path.Combine(candidate, "start-demo-original.ps1")) &&
        File.Exists(Path.Combine(candidate, "start-main-safe.ps1")) &&
        File.Exists(Path.Combine(directory.FullName, "docker-compose.demo.yml")))
    {
        scriptsDirectory = candidate;
        break;
    }
    directory = directory.Parent;
}

if (scriptsDirectory is null)
{
    Console.Error.WriteLine("No encontré el proyecto TiendaYa. Mantén este EXE dentro de su carpeta.");
    Console.WriteLine("Presiona Enter para cerrar.");
    Console.ReadLine();
    return 1;
}

Console.WriteLine("¿Qué entorno quieres iniciar?");
Console.WriteLine("  1. Presentación (DEMO original) - tienda :5173 y laboratorio :5174");
Console.WriteLine("  2. PRINCIPAL de desarrollo      - http://localhost:5173 (workers normales)");
Console.WriteLine("  0. Cancelar");
Console.Write("Elige 1 o 2: ");
var choice = Console.ReadLine()?.Trim();
if (choice is not ("1" or "2"))
{
    Console.WriteLine("Cancelado. No se inició nada.");
    return 0;
}

var script = Path.Combine(scriptsDirectory, choice == "1" ? "start-demo-original.ps1" : "start-main-safe.ps1");
Console.WriteLine(choice == "1"
    ? "Se iniciará solo la DEMO original, con Outbox y sin los demás workers."
    : "Se iniciará solo PRINCIPAL, con sus workers normales según backend/.env.");
Console.WriteLine("No se ejecutarán migraciones, seeds, backfills ni reindexaciones.");
Console.Write("¿Confirmas? [s/N]: ");
var confirmation = Console.ReadLine()?.Trim();
if (!string.Equals(confirmation, "s", StringComparison.OrdinalIgnoreCase) &&
    !string.Equals(confirmation, "si", StringComparison.OrdinalIgnoreCase) &&
    !string.Equals(confirmation, "sí", StringComparison.OrdinalIgnoreCase))
{
    Console.WriteLine("Cancelado. No se inició nada.");
    return 0;
}

var start = new ProcessStartInfo("powershell.exe")
{
    UseShellExecute = false,
    WorkingDirectory = directory!.FullName
};
start.ArgumentList.Add("-NoProfile");
start.ArgumentList.Add("-ExecutionPolicy");
start.ArgumentList.Add("Bypass");
start.ArgumentList.Add("-File");
start.ArgumentList.Add(script);

try
{
    using var process = Process.Start(start) ?? throw new InvalidOperationException("No se pudo abrir PowerShell.");
    process.WaitForExit();
    Console.WriteLine(process.ExitCode == 0 ? "Arranque completado." : "El arranque se detuvo por seguridad o error.");
    Console.WriteLine("Presiona Enter para cerrar.");
    Console.ReadLine();
    return process.ExitCode;
}
catch (Exception error)
{
    Console.Error.WriteLine($"No se inició TiendaYa: {error.Message}");
    Console.WriteLine("Presiona Enter para cerrar.");
    Console.ReadLine();
    return 1;
}
