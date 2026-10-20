param([string]$out)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W {
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
 public struct RECT { public int L, T, R, B; }
}
"@
$p = Get-Process PBIDesktop | Where-Object { $_.MainWindowTitle -like 'BI_*' } | Select-Object -First 1
$h = $p.MainWindowHandle
[W]::ShowWindow($h, 3) | Out-Null
Start-Sleep 2
$r = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
[W]::PrintWindow($h, $dc, 2) | Out-Null
$g.ReleaseHdc($dc); $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
"$($bmp.Width)x$($bmp.Height)"
