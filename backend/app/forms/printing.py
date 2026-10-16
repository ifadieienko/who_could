import html


def printable_value(spec, value):
    if spec["type"] != "table":
        return html.escape(str(value))
    columns = spec.get("columns", [])
    heading = "".join("<th>" + html.escape(c["label"] + (" · " + c["unit"] if c.get("unit") else "")) + "</th>" for c in columns)
    rows = "".join("<tr>" + "".join("<td>" + html.escape(str(row.get(c["key"]) if row.get(c["key"]) is not None else "")) + "</td>" for c in columns) + "</tr>" for row in (value or []))
    return '<table class="form-table"><thead><tr>' + heading + '</tr></thead><tbody>' + rows + '</tbody></table>'
