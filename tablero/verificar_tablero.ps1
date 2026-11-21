# Verifica el tablero abierto en Power BI Desktop: actualiza el modelo local y consulta los conteos clave.
# Uso (con EMI_EnRuta.pbip abierto):  powershell -ExecutionPolicy Bypass -File tablero\verificar_tablero.ps1
param([int]$Puerto = 0)
$ErrorActionPreference = "Stop"
if (-not $Puerto) {
  $archivo = Get-ChildItem "$env:USERPROFILE\Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces\*\Data\msmdsrv.port.txt",
                           "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces\*\Data\msmdsrv.port.txt" -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $archivo) { throw "Abre tablero\EMI_EnRuta.pbip en Power BI Desktop antes de verificar." }
  $Puerto = [int](Get-Content $archivo.FullName -Encoding Unicode)
}
$pkg = (Get-AppxPackage Microsoft.MicrosoftPowerBIDesktop).InstallLocation
$dll = @("$pkg\bin\Microsoft.PowerBI.AdomdClient.dll", "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll") |
       Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
Add-Type -Path $dll
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Puerto"); $cn.Open()
function Consultar($q) {
  $c = $cn.CreateCommand(); $c.CommandText = $q; $r = $c.ExecuteReader()
  while ($r.Read()) { $f = @(); for ($i = 0; $i -lt $r.FieldCount; $i++) { $f += "$($r.GetName($i))=$($r.GetValue($i))" }; $f -join " | " }
  $r.Close()
}
$c = $cn.CreateCommand(); $c.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"; $r = $c.ExecuteReader(); [void]$r.Read(); $db = $r.GetValue(0); $r.Close()
$c = $cn.CreateCommand(); $c.CommandText = '{"refresh":{"type":"full","objects":[{"database":"' + $db + '"}]}}'; [void]$c.ExecuteNonQuery()
"Modelo actualizado (puerto $Puerto)."
Consultar 'EVALUATE ROW("decisiones", [Decisiones], "asignadas", [Asignadas], "pendientes", [Pendientes o sin asignar], "participaciones", [Participaciones])'
Consultar 'EVALUATE SUMMARIZECOLUMNS(decisiones[origen_registro], decisiones[modalidad], "n", [Decisiones])'
Consultar 'EVALUATE ROW("suma_participaciones_cop", SUM(participaciones[costo_ida_cop]), "suma_decisiones_cop", SUM(decisiones[costo_viaje_elegido_cop]))'
Consultar 'EVALUATE CALCULATETABLE(SELECTCOLUMNS(linea_base, "codigo", linea_base[codigo_emi], "p90", linea_base[p90_min], "pct", linea_base[pct_cumple]), linea_base[vista] = "original", linea_base[codigo_emi] IN {"01", "02"})'
$cn.Close()
