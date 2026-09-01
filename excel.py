import pandas as pd

# Cambiar "action=default" por "download=1" en la URL de SharePoint
url_sharepoint = "https://corpsmu.sharepoint.com/:x:/r/sites/MedioAmbiente/_layouts/15/Doc.aspx?sourcedoc=%7B45232F23-A112-43BB-880C-FDE8CCA9981A%7D&file=Planilla_Base_Control%20Riles%202026_.xlsx&download=1"

# Pandas intentará abrir el recurso (requiere sesión/cookies válidas en el SSO)
df = pd.read_excel(url_sharepoint)