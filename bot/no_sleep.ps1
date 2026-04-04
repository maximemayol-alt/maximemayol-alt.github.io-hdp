# Empeche Windows de se mettre en veille tant que le bot tourne.
# Usage : clic droit > Executer avec PowerShell
# Ou lance depuis keep_alive.bat

Write-Host "Anti-veille actif — Windows ne se mettra pas en veille." -ForegroundColor Green
Write-Host "Ferme cette fenetre pour desactiver." -ForegroundColor Yellow
Write-Host ""

# Utilise SetThreadExecutionState pour empecher la veille
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class SleepBlocker {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);

    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;
}
"@

# Bloquer la veille
[SleepBlocker]::SetThreadExecutionState(
    [SleepBlocker]::ES_CONTINUOUS -bor
    [SleepBlocker]::ES_SYSTEM_REQUIRED
) | Out-Null

Write-Host "Veille bloquee. En attente..." -ForegroundColor Cyan

# Boucle infinie — le script bloque la veille tant qu'il tourne
while ($true) {
    Start-Sleep -Seconds 60
    # Rafraichir le blocage toutes les 60s
    [SleepBlocker]::SetThreadExecutionState(
        [SleepBlocker]::ES_CONTINUOUS -bor
        [SleepBlocker]::ES_SYSTEM_REQUIRED
    ) | Out-Null
}
