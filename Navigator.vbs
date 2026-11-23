Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
base = fs.GetParentFolderName(WScript.ScriptFullName)
shell.Run Chr(34) & base & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & base & "\launch_navigator.pyw" & Chr(34), 0, False
