def _render_in_list(values: list[str]) -> str:
    # Renderiza lista para IN ('a','b','c') con escape basico.
    safe = []
    for value in values:
        raw = str(value).replace("'", "''")
        safe.append(f"'{raw}'")
    return ", ".join(safe)
