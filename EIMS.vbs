' EIMS - Engineering Information Management System
' Silent Launcher - No console window
' Double-click this file to start EIMS without the black CMD window

Dim scriptDir
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = scriptDir

' Run streamlit with hidden window (0 = SW_HIDE, False = don't wait)
WshShell.Run "cmd /c py -m streamlit run app.py", 0, False

Set WshShell = Nothing
