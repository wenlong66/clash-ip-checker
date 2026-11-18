$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$element = [Windows.Automation.AutomationElement]
$descendants = [Windows.Automation.TreeScope]::Descendants
$walker = [Windows.Automation.TreeWalker]::ControlViewWalker
$buttonType = [Windows.Automation.PropertyCondition]::new($element::ControlTypeProperty, [Windows.Automation.ControlType]::Button)
$documentId = [Windows.Automation.PropertyCondition]::new($element::AutomationIdProperty, 'RootWebArea')

function Get-Document($process) {
    $process.Refresh()
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
        $window = $element::FromHandle($process.MainWindowHandle)
        if ($window.Current.ClassName -eq 'Tauri Window' -and !$window.Current.IsOffscreen) {
            return $window.FindFirst($descendants, $documentId)
        }
    }
}

try {
    $session = (Get-Process -Id $PID).SessionId
    $clash = @(Get-Process -Name 'clash-verge' -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $session -and $_.Path })
    if ($clash.Count -ne 1) { exit 10 }
    $process = $clash[0]
    $document = Get-Document $process
    if (!$document) {
        Start-Process -FilePath $process.Path
        for ($i = 0; $i -lt 20 -and !$document; $i++) {
            Start-Sleep -Milliseconds 250
            $document = Get-Document $process
        }
    }
    if (!$document) { exit 11 }

    # shortcut: Clash currently exposes subscription controls via UI Automation; prefer a public refresh API if one becomes available.
    $navigation = @($document.FindAll($descendants, $buttonType) | Where-Object {
        $_.Current.ClassName -match '\bMuiListItemButton-root\b' -and
        $_.Current.Name -match '^(订\s*阅|訂\s*閱|Profiles|Subscriptions)$'
    })
    if ($navigation.Count -ne 1) { exit 11 }
    if ($navigation[0].Current.ClassName -notmatch '\bMui-selected\b') {
        $navigation[0].GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
    }

    $name = [Windows.Automation.PropertyCondition]::new($element::NameProperty, $env:CLASH_REFRESH_PROFILE)
    for ($i = 0; $i -lt 16; $i++) {
        $labels = @($document.FindAll($descendants, $name) | Where-Object {
            $_.Current.ClassName -match '\bMuiTypography-h6\b'
        })
        if ($labels.Count -gt 1) { exit 12 }
        if ($labels.Count -eq 1) {
            $cardHeader = $walker.GetParent($labels[0])
            $refresh = @($cardHeader.FindAll($descendants, $buttonType) | Where-Object {
                $_.Current.Name -match '^(刷新|重新整理|Refresh)$'
            })
            if ($refresh.Count -ne 1 -or !$refresh[0].Current.IsEnabled) { exit 12 }
            $refresh[0].GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
            exit 0
        }
        Start-Sleep -Milliseconds 250
    }
    exit 12
} catch {
    exit 13
}
