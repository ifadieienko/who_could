"""workflows / service domain. Legacy API behavior is preserved."""




def stage_of(o):
    return next((s for s in o.workflow_snapshot if s["key"] == o.stage), {})

