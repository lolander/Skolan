def async_track_time_change(hass, action, hour=None, minute=None, second=None):
    """Anropa action när klockan matchar (som i Home Assistant). Värden tickar varje sekund."""
    def _lista(v):
        return None if v is None else (set(v) if isinstance(v, (list, tuple, set)) else {v})
    return hass.lagg_till_tid(action, _lista(hour), _lista(minute), _lista(second))
