'==========================================================================
' EIMS - Engineering Information Management System
' EIMS_Local_Test_v3  ::  Silent Launcher  (no black console window)
'==========================================================================
' Double-click this file to start EIMS with no CMD / no black screen.
'
' What it does
'   1. Checks that app.py and a real Python 3 interpreter are available.
'   2. Checks the required packages (and offers to install them if missing).
'   3. Starts the Streamlit server in a completely hidden window.
'   4. Waits until the application answers, then opens the browser.
'   5. Shows a clear message box if something fails - it never fails silently.
'
' Clicking this file twice is safe: if EIMS is already running on its port,
' the browser is simply opened again instead of starting a second copy.
'
' To STOP EIMS: close the browser tab and end the python.exe process that runs
' app.py in Task Manager (Details tab), or press Ctrl+C in the run_app.bat window.
'==========================================================================

Option Explicit

'--------------------------------- settings --------------------------------
Const APP_FILE      = "app.py"        ' must stay in the same folder
Const APP_PORT      = 8521            ' dedicated port for this EIMS copy
Const OPEN_BROWSER  = True            ' open the browser when EIMS is ready
Const START_WAIT    = 20              ' seconds allowed for the first answer
'-------------------------------------------------------------------------

Dim fso, sh, scriptDir, appPath, appUrl, pyExe, state, runCmd, i

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
appPath   = fso.BuildPath(scriptDir, APP_FILE)
appUrl    = "http://localhost:" & APP_PORT

'--- 0. app.py must sit next to this script -------------------------------
If Not fso.FileExists(appPath) Then
    StopWith "EIMS cannot be started." & vbCrLf & vbCrLf & _
             "The file below was not found:" & vbCrLf & appPath & vbCrLf & vbCrLf & _
             "Keep this EIMS.vbs file in the same folder as " & APP_FILE & "."
End If

'--- 1. resolve the real Python interpreter (py -3 avoids Store aliases) ----
pyExe = Capture("cmd /c py -3 -c " & ShQuote("import sys;print(sys.executable)"))
If Len(pyExe) = 0 Or InStr(1, pyExe, "\", vbBinaryCompare) = 0 Then
    StopWith "EIMS cannot be started." & vbCrLf & vbCrLf & _
             "Python 3 was not found on this computer." & vbCrLf & vbCrLf & _
             "Install Python 3 from python.org (keep the Python Launcher " & vbCrLf & _
             "option enabled), then run this file again."
End If

'--- 2. required packages --------------------------------------------------
If Not PackagesOK(pyExe) Then
    If MsgBox("The Python packages required by EIMS are not installed yet." & _
              vbCrLf & vbCrLf & "Do you want to install them now?" & vbCrLf & vbCrLf & _
              "This only needs to be done once.", vbYesNo + vbQuestion, _
              "EIMS - Setup") <> vbYes Then
        WScript.Quit 0
    End If
    MsgBox "Installing the required packages, please wait ...", vbInformation, "EIMS - Setup"
    sh.Run PipCmd(pyExe, scriptDir), 0, True          ' hidden, and wait for it
    If Not PackagesOK(pyExe) Then
        StopWith "The required packages could not be installed automatically." & _
                 vbCrLf & vbCrLf & _
                 "Please run this command in Command Prompt:" & vbCrLf & vbCrLf & _
                 PipCmd(pyExe, scriptDir)
    End If
End If

'--- 3. already running on its port? just show it --------------------------
If InStr(1, PortState(pyExe, APP_PORT), "UP", vbTextCompare) > 0 Then
    If OPEN_BROWSER Then OpenBrowser(appUrl)
    WScript.Quit 0
End If

'--- 4. start the server, hidden ------------------------------------------
sh.CurrentDirectory = scriptDir
runCmd = ShQuote(pyExe) & " -m streamlit run " & ShQuote(appPath) & _
         " --server.port " & APP_PORT & _
         " --server.headless true" & _
         " --browser.gatherUsageStats false"
sh.Run runCmd, 0, False                  ' 0 = hidden window, False = do not wait

'--- 5. wait until it answers, then open the browser ----------------------
For i = 1 To START_WAIT
    Wsh.Sleep 1000
    If InStr(1, PortState(pyExe, APP_PORT), "UP", vbTextCompare) > 0 Then
        If OPEN_BROWSER Then OpenBrowser(appUrl)
        WScript.Quit 0
    End If
Next

StopWith "EIMS was launched but did not answer on port " & APP_PORT & "." & _
         vbCrLf & vbCrLf & _
         "To read the error message, run this file from a visible window:" & _
         vbCrLf & vbCrLf & fso.BuildPath(scriptDir, "run_app.bat")

WScript.Quit 0

'==========================================================================
' helpers
'==========================================================================

Function ShQuote(s)
    ShQuote = Chr(34) & s & Chr(34)
End Function

Function PipCmd(py, dir)
    PipCmd = ShQuote(py) & " -m pip install -r " & ShQuote(fso.BuildPath(dir, "requirements.txt"))
End Function

' Runs a command and returns its standard output ("" on any failure).
Function Capture(cmd)
    Dim runner, proc, out
    On Error Resume Next
    Set runner = CreateObject("WScript.Shell")
    Set proc = runner.Exec(cmd)
    out = proc.StdOut.ReadAll
    proc.StdErr.ReadAll
    If Err.Number <> 0 Then
        Capture = ""
    Else
        Capture = Trim(Replace(Replace(out, vbCrLf, ""), vbLf, ""))
    End If
    On Error GoTo 0
End Function

' "UP" when something already listens on the port, otherwise "FREE".
Function PortState(py, port)
    Dim code
    code = "import socket;s=socket.socket();s.settimeout(2);" & _
           "print('UP' if s.connect_ex(('127.0.0.1'," & port & "))==0 else 'FREE')"
    PortState = Capture(ShQuote(py) & " -c " & ShQuote(code))
End Function

Function PackagesOK(py)
    Dim code
    code = "import streamlit,pandas,bs4,xlsxwriter,openpyxl,lxml;print('OK')"
    PackagesOK = (InStr(1, Capture(ShQuote(py) & " -c " & ShQuote(code)), "OK", vbTextCompare) > 0)
End Function

Sub OpenBrowser(url)
    sh.Run "cmd /c start " & ShQuote("") & " " & ShQuote(url), 0, False
End Sub

Sub StopWith(msg)
    MsgBox msg, vbCritical, "EIMS - Startup"
    WScript.Quit 1
End Sub
