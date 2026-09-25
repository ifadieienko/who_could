"""Permission compatibility without granting one new capability from another."""
JOB_ACTIONS = ("read", "create", "edit", "assign", "transition", "issue", "reopen")
GENERIC_PERMISSIONS = [*("jobs." + key for key in JOB_ACTIONS), "customers.read",
    "assets.read", "assets.write", "forms.manage", "workflows.manage",
    "documents.manage", "organization.manage"]


def effective_permissions(values, owner=False):
    result = set(values)
    for key in JOB_ACTIONS:
        if {"jobs." + key, "orders." + key} & result:
            result.update({"jobs." + key, "orders." + key})
    if {"contacts.read", "customers.read"} & result:
        result.update({"contacts.read", "customers.read"})
    if "templates.manage" in result:
        result.update({"forms.manage", "workflows.manage"})
    if {"forms.manage", "workflows.manage"} <= result:
        result.add("templates.manage")
    if owner:
        result.update(GENERIC_PERMISSIONS)
    return result
