' Run a command in a hidden window for Task Scheduler; wait and return its exit code.
' Usage: wscript.exe "run-hidden.vbs" "<full command line>"
WScript.Quit CreateObject("WScript.Shell").Run(WScript.Arguments(0), 0, True)
