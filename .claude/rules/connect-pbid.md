Learnings from Claude about connecting to semantic models via the connect-pbid skill

- Env is WSL: run scripts with `powershell.exe -File "$(wslpath -w script.ps1)"` (\\wsl.localhost path works). TOM DLLs already in %TEMP%\tom_nuget.
- Windows PowerShell 5.1 reads .ps1 as ANSI: prepend a UTF-8 BOM when the script has accented chars (M/DAX in Portuguese), else names get mangled.
- Adding a table in Desktop auto-creates relationships (autodetect) on columns like `identificacao`; check `$model.Relationships` before removing tables.
- Gold tables load via M function `fnSupabaseGold` (Supabase REST, pages of 1000 rows, `Accept-Profile: api` — materialized copies, not the slow gold views); params `SupabaseUrl`/`SupabaseAnonKey`. Service: cloud connection `con_supabase_monitoramento` (Web, Anonymous), schedule 08:30/10:30/14:30.
