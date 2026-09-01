import uvicorn
import webbrowser
import threading
import time
import sys
import os

# Evita que el programa colapse al intentar escribir en una consola que no existe
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

URL_INICIAL = "http://127.0.0.1:8000/"

def abrir_navegador():
    time.sleep(2)
    webbrowser.open(URL_INICIAL)

if __name__ == "__main__":
    threading.Thread(target=abrir_navegador, daemon=True).start()
    
    # IMPORTANTE: reload=False es obligatorio en un .pyw
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)