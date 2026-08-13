from pathlib import Path

from fastapi.templating import Jinja2Templates


WEB_DIR = Path(__file__).parent.parent

# Ogni cartella app/web/<feature>/templates/ viene trovata da sola:
# aggiungere una nuova feature non richiede toccare questo file.
TEMPLATE_DIRS = [
    str(path)
    for path in WEB_DIR.glob("*/templates")
    if path.is_dir()
]

templates = Jinja2Templates(directory=TEMPLATE_DIRS)
