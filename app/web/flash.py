from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

OK, ERR = "success", "error"


def redirect_with_flash(path: str, kind: str, msg: str, status: int = 303) -> RedirectResponse:
    qs = urlencode({"flash": kind, "msg": msg})
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{sep}{qs}", status_code=status)
