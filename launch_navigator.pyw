from pathlib import Path
import subprocess, socket, time, webbrowser, ctypes
base=Path(__file__).resolve().parent
python=base/'.venv/Scripts/python.exe'
def listening(port):
 try:
  with socket.create_connection(('127.0.0.1',port),timeout=.4): return True
 except OSError: return False
try:
 if not python.exists(): raise RuntimeError('Не найдено окружение Python в папке проекта.')
 if not listening(11434):
  import os
  candidates=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe',Path(os.environ.get('LOCALAPPDATA',''))/'Ollama/ollama.exe']
  for exe in candidates:
   if exe.exists():
    subprocess.Popen([str(exe),'serve'],creationflags=subprocess.CREATE_NO_WINDOW);break
 if not listening(8501):
  log=(base/'launcher.log').open('a',encoding='utf-8')
  subprocess.Popen([str(python),'-m','streamlit','run',str(base/'app.py'),'--server.address=127.0.0.1','--server.port=8501','--server.headless=true'],cwd=base,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
  for _ in range(60):
   if listening(8501):break
   time.sleep(.5)
  else: raise RuntimeError('Приложение не запустилось. Подробности в launcher.log.')
 webbrowser.open('http://127.0.0.1:8501')
except Exception as exc:
 ctypes.windll.user32.MessageBoxW(0,str(exc),'PostgreSQL Navigator',16)
