
$ErrorActionPreference = "Stop"
Add-Type -Path "$env:TEMP\tom_nuget\Microsoft.AnalysisServices.AdomdClient.retail.amd64\lib\net45\Microsoft.AnalysisServices.AdomdClient.dll"
$portFile = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces\*\Data\msmdsrv.port.txt" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $portFile) { $portFile = Get-ChildItem "$env:USERPROFILE\Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces\*\Data\msmdsrv.port.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 }
$port = (Get-Content $portFile.FullName -Encoding Unicode).Trim()
$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
$conn.Open()
function Q($titulo, $dax) {
  Write-Output "== $titulo"
  $cmd = $conn.CreateCommand(); $cmd.CommandText = $dax
  try {
    $r = $cmd.ExecuteReader()
    while ($r.Read()) { $l = @(); for ($i=0; $i -lt $r.FieldCount; $i++) { $l += "$($r.GetName($i))=$($r.GetValue($i))" }; Write-Output ($l -join " | ") }
    $r.Close()
  } catch { Write-Output "ERRO: $($_.Exception.Message)" }
}
Q "Totais" 'EVALUATE ROW("acompanhadas",[Proposições Acompanhadas],"radar",[Proposições em Radar],"monitoradas_SIM",[Total Proposições Monitoradas],"pautas_agendadas",[Pautas Agendadas],"canceladas",[Pautas Canceladas],"prox14",[Pautas Próximos 14 Dias],"atualizado",[Dados Atualizados Em],"referencia",[Data Referência],"mov",[Movimentação Mais Recente])'
Q "Nivel (todas)" 'EVALUATE GROUPBY(ADDCOLUMNS(VALUES(''gold vw_monitoramento''[id_proposicao]),"n",[Nível de Atenção]),[n],"q",SUMX(CURRENTGROUP(),1))'
Q "Nivel (acompanhadas)" 'EVALUATE GROUPBY(ADDCOLUMNS(CALCULATETABLE(VALUES(''gold vw_monitoramento''[id_proposicao]),''gold vw_monitoramento''[acompanhada]=TRUE()),"n",[Nível de Atenção]),[n],"q",SUMX(CURRENTGROUP(),1))'
Q "Pautas sem proposicao relacionada" 'EVALUATE ROW("orfas",COUNTROWS(FILTER(''gold vw_pautas_monitoradas'',ISBLANK(RELATED(''gold vw_monitoramento''[identificacao])))),"linhas",COUNTROWS(''gold vw_pautas_monitoradas''))'
Q "Prioridade (planilha)" 'EVALUATE GROUPBY(''gold dim_posicionamento_abcs'',''gold dim_posicionamento_abcs''[prioridade],"q",SUMX(CURRENTGROUP(),1))'
Q "Exemplos nivel>=2" 'EVALUATE TOPN(10,FILTER(ADDCOLUMNS(VALUES(''gold vw_monitoramento''[identificacao]),"n",[Nível de Atenção],"motivo",[Atenção Motivo]),[n]>=2),[n],DESC)'
$conn.Close()
