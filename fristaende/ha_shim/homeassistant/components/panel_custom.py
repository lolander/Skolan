async def async_register_panel(hass, **kw) -> None:
    """Kom ihåg vilken webbkomponent appens startsida ska ladda."""
    hass.panel = kw
