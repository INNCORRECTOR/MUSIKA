from fastapi.templating import Jinja2Templates

from app.config import build_public_asset_url, normalize_stored_asset_url

templates = Jinja2Templates(directory="templates")
templates.env.filters["asset_url"] = normalize_stored_asset_url
templates.env.globals["default_artist_hero_url"] = build_public_asset_url("artistart.png")
