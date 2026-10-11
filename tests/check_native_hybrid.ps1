# Interactive Windows regression check. Run from the repository root with ORION open.
# Exercises only window controls; never activates the microphone or submits tasks.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path 'test_output' | Out-Null
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class OrionHybridWindow {
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string cls,string title);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h,int index);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [StructLayout(LayoutKind.Sequential)] public struct Point { public int X,Y; }
 [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h,ref Point p);
 [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int command);
 [DllImport("user32.dll")] public static extern void keybd_event(byte key,byte scan,uint flags,UIntPtr extra);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint x,uint y,uint data,UIntPtr extra);
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
"@
[OrionHybridWindow]::SetProcessDPIAware() | Out-Null
$orionGuiDeadline=(Get-Date).AddSeconds(30)
$orionGuiHandle=[IntPtr]::Zero
while ($orionGuiHandle -eq [IntPtr]::Zero -and (Get-Date) -lt $orionGuiDeadline) {
 $orionGuiHandle=[OrionHybridWindow]::FindWindow([NullString]::Value,'ORION | Mission Control')
 if ($orionGuiHandle -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 200 }
}
if ($orionGuiHandle -eq [IntPtr]::Zero) { throw 'Native ORION window is not visible to this GUI session' }
[OrionHybridWindow]::ShowWindow($orionGuiHandle,9) | Out-Null
function Get-OrionBounds {
 $orionGuiRect=New-Object OrionHybridWindow+Rect
 [OrionHybridWindow]::GetWindowRect($orionGuiHandle,[ref]$orionGuiRect) | Out-Null
 return $orionGuiRect
}
function Invoke-OrionControl([string]$controlName) {
 $orionElement=[System.Windows.Automation.AutomationElement]::FromHandle($orionGuiHandle)
 $orionCondition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$controlName)
 $orionButton=$orionElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$orionCondition)
 if ($null -ne $orionButton) {
   $orionPattern=$orionButton.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
   $orionPattern.Invoke()
 } else {
   [OrionHybridWindow]::SetForegroundWindow($orionGuiHandle) | Out-Null
   if ([OrionHybridWindow]::GetForegroundWindow() -ne $orionGuiHandle) { throw 'ORION is not foreground; no pointer input sent' }
   $orionClient=New-Object OrionHybridWindow+Rect
   [OrionHybridWindow]::GetClientRect($orionGuiHandle,[ref]$orionClient) | Out-Null
   $orionOrigin=New-Object OrionHybridWindow+Point
   [OrionHybridWindow]::ClientToScreen($orionGuiHandle,[ref]$orionOrigin) | Out-Null
   $orionScale=[OrionHybridWindow]::GetDpiForWindow($orionGuiHandle)/96.0
   if ($controlName -eq 'Expand Mission Control') { $orionClickX=$orionClient.Right-67*$orionScale;$orionClickY=29*$orionScale }
   elseif ($controlName -eq 'Collapse to floating mode') { $orionClickX=$orionClient.Right-445*$orionScale;$orionClickY=34.5*$orionScale }
   elseif ($controlName -eq 'Minimize ORION') { $orionClickX=$orionClient.Right-27*$orionScale;$orionClickY=29*$orionScale }
   else { throw 'Unsupported native control fallback' }
   [OrionHybridWindow]::SetCursorPos([int]($orionOrigin.X+$orionClickX),[int]($orionOrigin.Y+$orionClickY)) | Out-Null
   [OrionHybridWindow]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
   [OrionHybridWindow]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
 }
 Start-Sleep -Milliseconds 600
}
function Save-OrionCapture([string]$name) {
 [OrionHybridWindow]::SetForegroundWindow($orionGuiHandle) | Out-Null
 Start-Sleep -Milliseconds 300
 if ([OrionHybridWindow]::GetForegroundWindow() -ne $orionGuiHandle) { throw 'ORION not foreground; capture skipped' }
 $orionBounds=Get-OrionBounds
 $orionImage=New-Object System.Drawing.Bitmap(($orionBounds.Right-$orionBounds.Left),($orionBounds.Bottom-$orionBounds.Top))
 $orionDraw=[System.Drawing.Graphics]::FromImage($orionImage)
 try { $orionDraw.CopyFromScreen($orionBounds.Left,$orionBounds.Top,0,0,$orionImage.Size);$orionImage.Save((Join-Path $PWD "test_output/$name")) }
 finally { $orionDraw.Dispose();$orionImage.Dispose() }
}
# Start from a known mode even if the user left the desktop expanded.
if (([OrionHybridWindow]::GetWindowLong($orionGuiHandle,-20) -band 8) -eq 0) {
 Invoke-OrionControl 'Collapse to floating mode'
}
$orionInitial=Get-OrionBounds
$orionInitialTopmost=([OrionHybridWindow]::GetWindowLong($orionGuiHandle,-20) -band 8) -ne 0
Write-Output "Compact window: width=$($orionInitial.Right-$orionInitial.Left), height=$($orionInitial.Bottom-$orionInitial.Top), topmost=$orionInitialTopmost"
Save-OrionCapture 'hybrid-native-compact.png'
Invoke-OrionControl 'Expand Mission Control'
$orionExpanded=Get-OrionBounds
$orionExpandedTopmost=([OrionHybridWindow]::GetWindowLong($orionGuiHandle,-20) -band 8) -ne 0
Write-Output "Expanded window: width=$($orionExpanded.Right-$orionExpanded.Left), height=$($orionExpanded.Bottom-$orionExpanded.Top), topmost=$orionExpandedTopmost"
Save-OrionCapture 'hybrid-native-expanded.png'
Invoke-OrionControl 'Collapse to floating mode'
$orionCollapsedTopmost=([OrionHybridWindow]::GetWindowLong($orionGuiHandle,-20) -band 8) -ne 0
Write-Output "Collapsed topmost=$orionCollapsedTopmost"
Invoke-OrionControl 'Expand Mission Control'
$orionRestored=Get-OrionBounds
if (($orionRestored.Right-$orionRestored.Left) -ne ($orionExpanded.Right-$orionExpanded.Left) -or ($orionRestored.Bottom-$orionRestored.Top) -ne ($orionExpanded.Bottom-$orionExpanded.Top)) { throw 'Expanded dimensions drifted during a second mode switch' }
Invoke-OrionControl 'Collapse to floating mode'
Write-Output 'PASS: expanded dimensions restored without drift across repeated mode switches'


if (-not $orionInitialTopmost -or $orionExpandedTopmost -or -not $orionCollapsedTopmost) { throw 'Unexpected window topmost state' }
Invoke-OrionControl 'Minimize ORION'
if (-not [OrionHybridWindow]::IsIconic($orionGuiHandle)) { throw 'Minimize did not take effect' }
[OrionHybridWindow]::keybd_event(17,0,0,[UIntPtr]::Zero)
[OrionHybridWindow]::keybd_event(16,0,0,[UIntPtr]::Zero)
[OrionHybridWindow]::keybd_event(32,0,0,[UIntPtr]::Zero)
[OrionHybridWindow]::keybd_event(32,0,2,[UIntPtr]::Zero)
[OrionHybridWindow]::keybd_event(16,0,2,[UIntPtr]::Zero)
[OrionHybridWindow]::keybd_event(17,0,2,[UIntPtr]::Zero)
Start-Sleep -Milliseconds 800
if ([OrionHybridWindow]::IsIconic($orionGuiHandle)) { throw 'Global shortcut did not restore ORION' }
Write-Output 'PASS: visible compact, expanded, collapsed, minimize and Ctrl+Shift+Space restoration. No microphone was activated.'
